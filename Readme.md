Copyright Szabo Cristina-Andreea 2024-2025
# Switch Implementation

## Project Description
This project implements a network switch with VLAN and Spanning Tree Protocol (STP) support. The switch handles Ethernet frames, manages VLAN tagging, and ensures loop-free topology using STP.

## Main Features
1. **Frame Forwarding**:
   - If the destination MAC address is unicast and present in the MAC table, the frame is sent to the corresponding port.
   - If the destination MAC is not in the table or is a broadcast address, the frame is broadcast to all ports.

2. **VLAN Handling**:
   - Frames without a VLAN tag are assigned a VLAN based on the port's configuration from the VLAN table.
   - For trunk ports, VLAN tags are added or removed as needed.
   - For access ports, frames are only forwarded if their VLAN matches the port's configured VLAN.

3. **Spanning Tree Protocol (STP)**:
   - Initializes by setting trunk ports to "blocking" mode to prevent loops.
   - Switches initially assume themselves as the root and send BPDU (Bridge Protocol Data Unit) packets.
   - Upon receiving BPDU packets, switches determine the root bridge based on priority and adjust port states accordingly to maintain a loop-free network.

## BPDU Packet Structure
- Contains destination and source MAC addresses.
- Includes fields: `bpdu_root_id`, `bpdu_root_path_cost`, and `bpdu_own_id`.

