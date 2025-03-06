#!/usr/bin/python3
import sys
import struct
import wrapper
import threading
import time
from wrapper import recv_from_any_link, send_to_link, get_switch_mac, get_interface_name

def parse_ethernet_header(data):
    # Unpack the header fields from the byte array
    #dest_mac, src_mac, ethertype = struct.unpack('!6s6sH', data[:14])
    dest_mac = data[0:6]
    src_mac = data[6:12]
    
    # Extract ethertype. Under 802.1Q, this may be the bytes from the VLAN TAG
    ether_type = (data[12] << 8) + data[13]

    vlan_id = -1
    # Check for VLAN tag (0x8100 in network byte order is b'\x81\x00')
    if ether_type == 0x8200:
        vlan_tci = int.from_bytes(data[14:16], byteorder='big')
        vlan_id = vlan_tci & 0x0FFF  # extract the 12-bit VLAN ID
        ether_type = (data[16] << 8) + data[17]

    return dest_mac, src_mac, ether_type, vlan_id

def create_vlan_tag(vlan_id):
    # 0x8100 for the Ethertype for 802.1Q
    # vlan_id & 0x0FFF ensures that only the last 12 bits are used
    return struct.pack('!H', 0x8200) + struct.pack('!H', vlan_id & 0x0FFF)

# variabile pentru stp
own_bridge_id = None
root_port = 0
root_path_cost = 0
root_bridge_id = 0

# adresa mac destinatie a unui pachet bpdu
dest_mac_bpdu = b"\x01\x80\xC2\x00\x00\x00"
# tabela care contine vlan-urile porturilor access si T pentru trunk-uri
vlan_table = {}
# tabela care contine adresele mac ale porturilor
mac_table = {}
# tabela care retine daca un port e blocking sau listening
port_state_table = {}
# flag ca sa stiu daca adaug sau scot vlan tag-ul
ok = -1
interfaces = []

# functie care parseaza fisierul de configuratie al unui switch
def parse_config(config_file):
    with open(config_file, 'r') as f:
        lines = f.readlines()
        switch_priority = int(lines[0].strip())
        for line in lines[1:]:
            line = line.strip()
            parts = line.split()
            # vlan-ul e numar pentru ca e port tip access
            if parts[1] != 'T':
                vlan_table[parts[0]] = int(parts[1])
            # trunk-urile accepta orice vlan, pun T ca sa diferentiez de access
            elif parts[1] == 'T':
                vlan_table[parts[0]] = 'T'
    return switch_priority

# verific daca adresa este unicast
def is_unicast(address):
    return int(address.split(":")[0], 16) & 1 == 0

# functie care adauga sau scoate vlan tag-ul
def handle_vlan_tag(data, length, vlan_id, ok):
    if ok == 1:
        # adaug
        return data[0:12] + create_vlan_tag(vlan_id) + data[12:], length + 4
    else:
        # scot
        return data[0:12] + data[16:], length - 4

# functie care trimite un frame in functie de portul destinatie
def send_frame(dest_interface, vlan_id, data, length):
    global ok
    # portul e trunk, verific daca e blocking si trimit cu tag
    if vlan_table[get_interface_name(dest_interface)] == 'T':
        ok = 1
        data, length = handle_vlan_tag(data, length, vlan_id, ok)
        if port_state_table[get_interface_name(dest_interface)] != "block":
            send_to_link(dest_interface, len(data), data)
    # verific ca vlan-ul sa fie acelasi pentru portul curent si destinatie
    elif vlan_id == vlan_table[get_interface_name(dest_interface)]:
        send_to_link(dest_interface, len(data), data)

# functie pentru a transmite un frame pe toate porturile,
# cu exceptia celui de pe care vine
def broadcast(incoming_interface, vlan_id, data, length):
    for i in interfaces:
        if i != incoming_interface:
            send_frame(i, vlan_id, data, length)

# vad daca frame-ul trebuie trimis catre o anumita adresa sau broadcast
def forward_frame(dest_mac, incoming_interface, data, length, vlan_id):
    # daca adresa e unicast, verific daca e in mac table si trimit catre adresa
    # daca nu e, o trimit catre toate celelalte
    if is_unicast(dest_mac):
        if dest_mac in mac_table:
            send_frame(mac_table[dest_mac], vlan_id, data, length)
        else:
            broadcast(incoming_interface, vlan_id, data, length)
    # trebuie sa trimit broadcast
    else:
        broadcast(incoming_interface, vlan_id, data, length)

# functie care trimite pachete bpdu la cate o secunda
def send_bpdu_every_sec():
    while True:
        # daca switch-ul e root trimit broadcast cu pachetul bpdu al root-ului
        if own_bridge_id == root_bridge_id:
            for i in interfaces:
                src = get_switch_mac()
                bpdu = create_bpdu(dest_mac_bpdu, src, own_bridge_id, 0, own_bridge_id)
                # trimit daca portul e trunk si nu e blocking, ca sa ajunga la restul switch-urilor
                if vlan_table[get_interface_name(i)] == 'T':
                    if port_state_table[get_interface_name(i)] != "blocking":
                        send_to_link(i, len(bpdu), bpdu)
        time.sleep(1)

# functie care creeaza bpdu cu adresele mac si cele 3 campuri importante din cerinta
def create_bpdu(dest_mac_bpdu, src_mac, bpdu_bridge_id, bpdu_root_path_cost, bpdu_root_id):
    bpdu = struct.pack("!6s6sIII", dest_mac_bpdu, src_mac, \
                       bpdu_bridge_id, bpdu_root_path_cost, bpdu_root_id)
    return bpdu

# functie care se ocupa cu bpdu-urile primite
def handle_bpdu(bpdu_bridge_id, bpdu_root_path_cost, bpdu_root_id, interface):
    global port_state_table, own_bridge_id, root_path_cost, root_bridge_id, root_port
    # noul cost in caz ca e mai bun
    new_cost = bpdu_root_path_cost + 10
    # id-ul switch-ului e mai mic decat al root-ului, devine root
    if bpdu_root_id < root_bridge_id:
        root_port = interface
        # se updateaza costul
        root_path_cost = new_cost
        # daca eram root punem toate porturile mai putin root port pe blocking
        if own_bridge_id == root_bridge_id:
            for i in interfaces:
                if vlan_table[get_interface_name(i)] == 'T':
                    if i != root_port:
                        port_state_table[get_interface_name(i)] = "block"
        root_bridge_id = bpdu_root_id
        # pun root port pe listen
        port_state_table[get_interface_name(root_port)] = "listen"
        # updatez bpdu-ul si l trimit pe porturile trunk care nu-s blocking
        for i in interfaces:
            if vlan_table[get_interface_name(i)] == 'T' and i != root_port:
                src = get_switch_mac()
                new = create_bpdu(dest_mac_bpdu, src, own_bridge_id, \
                                  root_path_cost, root_bridge_id)
                if port_state_table[get_interface_name(i)] != "block":
                    send_to_link(i, len(new), new)
    # daca path-ul e mai avantajos pentru root
    elif bpdu_root_id == root_bridge_id:
        if interface == root_port:
            if new_cost < root_path_cost:
                root_path_cost = new_cost
        elif interface != root_port:
            if bpdu_root_path_cost > root_path_cost:
                if port_state_table[get_interface_name(interface)] == "block":
                    port_state_table[get_interface_name(interface)] = "listen"
    # pun portul curent pe blocking
    elif bpdu_bridge_id == own_bridge_id:
        port_state_table[get_interface_name(interface)] = "block"
    else:
        # dau discard la bpdu
        return
    # daca e root, pun pe listening porturile
    if own_bridge_id == root_bridge_id:
        for i in interfaces:
            if port_state_table[get_interface_name(i)] == "block":
                port_state_table[get_interface_name(i)] = "listen"    

def main():
    switch_id = sys.argv[1]
    config_file = f'configs/switch{switch_id}.cfg'
    global port_state_table, own_bridge_id
    global root_path_cost, root_bridge_id, root_port
    # parsez fisierul de configuratie si obtin prioritatea switch
    switch_priority = parse_config(config_file)

    num_interfaces = wrapper.init(sys.argv[2:])
    global interfaces, ok
    interfaces = range(0, num_interfaces)

    # initializam stp-ul, punand pe blocking toate porturile
    for i in interfaces:
        port_state_table[get_interface_name(i)] = "block"

    own_bridge_id = switch_priority
    root_bridge_id = own_bridge_id

    # daca switch-ul e root se pun porturile pe listen
    # initial toate cred ca sunt root
    if own_bridge_id == root_bridge_id:
        for i in interfaces:
            port_state_table[get_interface_name(i)] = "listen"

    root_path_cost = 0

    t = threading.Thread(target=send_bpdu_every_sec)
    t.start()

    while True:
        interface, data, length = recv_from_any_link()

        dest_mac, src_mac, ethertype, vlan_id = parse_ethernet_header(data)
        dest_mac = ':'.join(f'{b:02x}' for b in dest_mac)
        src_mac = ':'.join(f'{b:02x}' for b in src_mac)

        # daca adresa destinatie e cea de broadcast bpdu
        if dest_mac == "01:80:c2:00:00:00":
            # extrag datele din bpdu si le pasez functiei de handle_bpdu
            dest_mac, src_mac, bpdu_bridge_id, bpdu_root_path_cost, bpdu_root_id \
                = struct.unpack("!6s6sIII", data)
            handle_bpdu(bpdu_bridge_id, bpdu_root_path_cost, bpdu_root_id, interface)
        else:
            # vlan id-ul e -1 asa ca iau din vlan_table
            if vlan_id == -1:
                vlan_id = vlan_table[get_interface_name(interface)]
            else:
                # a venit de pe port trunk, deci scot vlan tag-ul
                ok = 0
                data, length = handle_vlan_tag(data, length, vlan_id, ok)
            # adaug in mac table
            mac_table[src_mac] = interface
            # trimit frame-ul
            if vlan_id != 'T':
                forward_frame(dest_mac, interface, data, length, vlan_id)

if __name__ == "__main__":
    main()
