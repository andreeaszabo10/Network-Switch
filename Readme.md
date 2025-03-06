Copyright Szabo Cristina-Andreea 2024-2025
# Implementare switch

1. Flow-ul forward_frame:
- daca adresa mac destinatie este unicast, verific daca se afla in tabela mac, apoi trimit frame-ul, iar daca nu se afla o trimit pe toate porturile
- adresa destinatie nu e unicast, asa ca transmit frame-ul pe toate porturile
2. Verific pentru un frame daca vlan-ul este -1, si daca este ii dau vlan-ul corespunzator din vlan_table, care este citita din fisierele de configuratie al switch-urilor. Altfel, scot vlan tag-ul frame-ului. Apoi cand trimit frame-urile in functia forward_frame, daca trimit pe un port trunk adaug vlan tag-ul inapoi. De asemenea, daca portul pe care trimit este de tip access, verific daca vlan-ul frame-ului este acelasi cu cel al destinatiei, iar daca nu este, nu trimit pe acel port.
3. Am implementat protocolul de STP pentru a evita buclele in retea astfel:
- initializez protocolul punand toate porturile trunk de pe switch pe modul blocking, initial toate switch-urile sunt setate ca root, iar daca este root, toate porturile sunt puse pe listening. 
- se trimit pachete bpdu de la toate switch-urile, pentru ca toate cred ca sunt root
- cand primesc pachetul, switch-urile aleg root-switch-ul cu prioritatea cea mai mica si trimit pachetul actualizat mai departe, avand grija sa puna porturile trunk pe blocking, mai putin root port

Bpdu-ul contine adresele mac destinatie si sursa, si cele 3 campuri importante care sunt folosite din pachet: bpdu_root_id, bpdu_root_path_cost si bpdu_own_id