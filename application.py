import os
import socket
import threading
import time
import struct
import random
import tkinter as tk
import queue

running = True
connected = False
setting = False
sending = False

wait = 0
last_keepalive_sent = 0
last_keepalive_ack = time.time()

flags_types = {
    # Handshake flags
    'FLAG_HS1': 0b10000000,
    'FLAG_HS2': 0b10001000,
    'FLAG_HS3': 0b10001001,
    # Exit flags
    'FLAG_EXIT': 0b01000000,
    'FLAG_EXIT_ACK': 0b01001000,
    # Keepalive flags
    'FLAG_KEEPALIVE': 0b00100000,
    'FLAG_KEEPALIVE_ACK': 0b00101000,
    # Message flags
    'FLAG_MSG': 0b00010010,
    'FLAG_MSG_ACK': 0b00011010,
    'FLAG_MSG_REQ': 0b00010110,
    'FLAG_MSG_PAR': 0b10010010,
    'FLAG_MSG_PAR_ACK': 0b10011010,
    'FLAG_MSG_PAR_REQ': 0b10010110,
    'FLAG_MSG_FRAG': 0b00010011,
    # Data(file) flags
    'FLAG_DATA_PAR': 0b10010000,
    'FLAG_DATA_PAR_ACK': 0b10011000,
    'FLAG_DATA_PAR_REQ': 0b10010100,
    'FLAG_DATA': 0b00010000,
    'FLAG_DATA_ACK': 0b00011000,
    'FLAG_DATA_REQ': 0b00010100, }

########################################################################################################################
# print of messages when 2 threads are printing
print_lock = threading.Lock()
message_queue = queue.Queue()

def thread_safe_print(out):
    with print_lock:
        message_queue.put(out)
        try:
            if not message_queue.empty():
                msg = message_queue.get_nowait()
                print(msg)
        except queue.Empty:
            pass


########################################################################################################################
#message operations
#getting checksum with CRC16-CCITT
def get_checksum(data):
    if isinstance(data, str):
        data = data.encode('utf-8')
    poly = 0x1021
    crc = 0xFFFF
    for byte in data:
        #XOR
        crc ^= (byte << 8)
        for _ in range(8):
            #checking first bite
            if crc & 0x8000:
                #moving one to left and then XOR
                crc = (crc << 1) ^ poly
            else:
                crc <<= 1
            #ensuring its 2B long
            crc &= 0xFFFF
    return crc

#encoding message based on my protocol
def encode_message(flags, frag_num, window_size, data):
    if isinstance(data, str):
        data = data.encode('utf-8')
    elif data is None:
        data = b''
    header_format = '!B I H H'
    checksum = get_checksum(data)
    #simulating corruption of message
    if corruption_rate != 0:
        if data and random.uniform(0, 100) < corruption_rate:
            corrupt_byte_index = random.randint(0, len(data) - 1)
            corrupted_byte = random.randint(0, 255)
            while data[corrupt_byte_index] == corrupted_byte:
                corrupted_byte = random.randint(0, 255)
            data = data[:corrupt_byte_index] + bytes(corrupted_byte) + data[corrupt_byte_index + 1:]
    header = struct.pack(header_format, flags, frag_num, window_size, checksum)
    return header + data

#decoding message based on my protocol
def decode_message(msg):
    header_format = '!B I H H'
    header = msg[:9]
    flags, frag_num, window_size, checksum = struct.unpack(header_format, header)
    data = msg[9:]
    return {
        'flags': flags,
        'fragment_number': frag_num,
        'window_size': window_size,
        'checksum': checksum,
        'data': data}


########################################################################################################################
#status update(canvas update)
def update_status_info():
    global wait
    wait = 0
    if connected and not sending:
        #connected and not sending
        status_label.config(text="Connected", fg="green")
        connect_button.config(state="disabled")
        disconnect_button.config(state="normal")
        message_button.config(state="normal")
        file_button.config(state="normal")
        message_entry.config(state="normal")
        file_entry.config(state="normal")
        settings_button.config(state="normal")
    elif connected and sending:
        #connected and sending
        status_label.config(text="Sending", fg="orange")
        disconnect_button.config(state="disabled")
        connect_button.config(state="disabled")
        message_button.config(state="disabled")
        file_button.config(state="disabled")
        message_entry.config(state="disabled")
        file_entry.config(state="disabled")
        settings_button.config(state="disabled")
    else:
        #disconnected
        thread_safe_print("\nDisconnected\n")
        status_label.config(text="Disconnected", fg="red")
        disconnect_button.config(state="disabled")
        connect_button.config(state="normal")
        message_button.config(state="disabled")
        file_button.config(state="disabled")
        message_entry.config(state="disabled")
        file_entry.config(state="disabled")
        settings_button.config(state="normal")


########################################################################################################################
# connection initialization
def send_HS1(remaining_tries):
    global sending
    sending = True
    #if not connected HS1 is sent
    if not connected:
        encoded_msg = encode_message(flags_types['FLAG_HS1'], 0, 0, "")
        send_sock.sendto(encoded_msg, (peer_ip, peer_port))
        thread_safe_print("sent HS1")
        #checking if message HS2 was delivered
        root.after(500, lambda: check_connection(remaining_tries - 1))

def check_connection(remaining_tries):
    if not connected:
        #if there are tries, try again
        if remaining_tries > 0:
            thread_safe_print(f"\nUnable to reach, remaining tries: {remaining_tries}\n")
            send_HS1(remaining_tries)
        #if no tries left connection failed
        else:
            thread_safe_print("\nUnable to reach\n")
            update_output_text("Unable to reach")
    else:
        update_output_text("Connected")
        thread_safe_print("\nConnected\n")


########################################################################################################################
# disconnection initialization
def send_EXIT(remaining_tries):
    global sending
    sending = True
    update_status_info()
    #if connected exit message is sent
    if connected:
        encoded_msg = encode_message(flags_types['FLAG_EXIT'], 0, 0, "")
        thread_safe_print("\nsent EXIT")
        send_sock.sendto(encoded_msg, (peer_ip, peer_port))
        #checking if disconnected
        root.after(500, lambda: check_disconnection(remaining_tries - 1))


def check_disconnection(remaining_tries):
    global connected
    if connected:
        #if remaining tries, try again
        if remaining_tries > 0:
            thread_safe_print(f"\nUnable to reach, remaining tries: {remaining_tries}\n")
            send_EXIT(remaining_tries)
        #if no remaining tries, peer not reached, disconnected
        else:
            thread_safe_print("\nPeer not reached\n")
            update_output_text("Peer not reached")
            connected = False
            update_status_info()



########################################################################################################################
# keep-alive
def keep_alive():
    global wait, send_keepalive
    while running:
        time.sleep(0.1)
        wait = 0
        send_keepalive = False
        #if not sending and connected start keepalive
        while not sending and connected and running:
            time.sleep(0.1)
            wait += 0.1
            if sending:
                break
            #after 5 seconds nad not sending and keepalive wasn't sent
            if wait >= 5 and not sending and not send_keepalive:
                send_keepalive = True
                send_KEEPALIVE_msg(3)
                wait = 0

#send and check keepalive
def send_KEEPALIVE_msg(remaining_tries):
    global delivered_keepalive
    if connected and not sending:
        delivered_keepalive = False
        encoded_msg = encode_message(flags_types['FLAG_KEEPALIVE'], 0, 0, "")
        thread_safe_print("sent KEEPALIVE")
        send_sock.sendto(encoded_msg, (peer_ip, peer_port))
        #check if keepalive ack was delivered
        root.after(5000, lambda: check_KEEPALIVE(remaining_tries - 1))


def check_KEEPALIVE(remaining_tries):
    global connected, send_keepalive
    if connected and not sending:
        if not delivered_keepalive:
            #if not delivered try again
            if remaining_tries > 0:
                thread_safe_print(f"\nUnable to reach, remaining tries: {remaining_tries}\n")
                send_KEEPALIVE_msg(remaining_tries)
            #if no tries remaining disconnected
            else:
                thread_safe_print("\nPeer not reached\n")
                update_output_text("Peer disconnected")
                connected = False
                update_status_info()
        else:
            send_keepalive = False


########################################################################################################################
# send message
def send_message(remaining_tries):
    global delivered, text, sending, requested
    sending = True
    text = message_entry.get()
    delivered = False
    requested = False
    #sending fragmented text
    if len(text) > max_fragment_size:
        send_message_parameters()
    #sending not fragmented text
    else:
        if connected and text:
            encoded_msg = encode_message(flags_types['FLAG_MSG'], 0, 0, text)
            send_sock.sendto(encoded_msg, (peer_ip, peer_port))
            thread_safe_print(f"\nSent msg:{text}")
            #check if msg delivered
            root.after(500, lambda: check_msg_delivery(remaining_tries))


def check_msg_delivery(remaining_tries):
    global connected
    if connected:
        #if requested send again
        if requested:
            send_message(remaining_tries)
        #if not delivered try again or disconnect
        elif not delivered:
            if remaining_tries > 1:
                thread_safe_print(f"\nUnable to reach, remaining tries:{remaining_tries - 1}\n")
                send_message(remaining_tries - 1)
            else:
                update_output_text("Message not delivered")
                thread_safe_print("\nPeer not reached\n")
                connected = False
                update_status_info()

#sending text parameters
def send_message_parameters():
    global sending, delivered, requested
    message = message_entry.get().encode('utf-8')
    last_fragment = len(message) // max_fragment_size
    #window size should be less than half of fragment number
    if last_fragment / 2 >= 65535:
        window_size = 65535
    else:
        window_size = last_fragment // 2
        if window_size == 0:
            window_size = 1
    encoded_msg = encode_message(flags_types['FLAG_MSG_PAR'], last_fragment, window_size, '')
    send_sock.sendto(encoded_msg, (peer_ip, peer_port))
    #information about transfer
    thread_safe_print(f"\nreceived MSG PAR:")
    thread_safe_print(f"Last fragment number: {last_fragment}")
    thread_safe_print(f"Number of fragments: {last_fragment+1}")
    thread_safe_print(f"Max window size: {window_size}")
    thread_safe_print(f"Size of text: {len(message)}")
    thread_safe_print(f"Fragment size: {max_fragment_size}")
    #if last fragment has different size, the size is printed
    if len(message[last_fragment * max_fragment_size:])!=max_fragment_size:
        thread_safe_print(f"Last fragment size: {len(message[last_fragment * max_fragment_size:])}")
    thread_safe_print("\n")
    #check for delivery
    root.after(500, lambda: check_msg_parameters(3, last_fragment, window_size))


def check_msg_parameters(remaining_tries, last_fragment, window_size):
    global connected
    if connected:
        #if requested send again
        if requested:
            encoded_msg = encode_message(flags_types['FLAG_MSG_PAR'], last_fragment, window_size, '')
            send_sock.sendto(encoded_msg, (peer_ip, peer_port))
            thread_safe_print(f"Sent MSG_PAR")
            root.after(500, lambda: check_msg_parameters(remaining_tries, last_fragment, window_size))
        #if not delivered try again or status is disconnected
        elif not delivered:
            if remaining_tries > 1:
                thread_safe_print(f"\nUnable to reach, remaining tries:{remaining_tries - 1}\n")
                encoded_msg = encode_message(flags_types['FLAG_MSG_PAR'], last_fragment, window_size, '')
                send_sock.sendto(encoded_msg, (peer_ip, peer_port))
                thread_safe_print(f"Sent MSG_PAR")
                root.after(500,
                           lambda: check_msg_parameters(remaining_tries - 1, last_fragment, window_size))
            else:
                update_output_text("Parameters not delivered")
                update_output_text("Peer not reached")
                connected = False
                update_status_info()
        #if delivered start sending
        elif delivered:
            send_fragmented_msg(last_fragment, window_size)


def send_fragmented_msg(last_fragment_number, window_size):
    global sf, requested_fragments, fragment_lock, ack_fragments, message, file_content, ack_received, connected, tries, encoded_fragments

    message = message_entry.get()
    #first fragment not delivered
    sf = 0
    encoded_fragments = {}
    requested_fragments = queue.Queue()
    #info about fragments delivery
    ack_fragments = [False] * (last_fragment_number + 1)
    #encoding messages
    for i in range(last_fragment_number + 1):
        if i == last_fragment_number:
            fragment = message[i * max_fragment_size:]
        else:
            fragment = message[i * max_fragment_size:(i + 1) * max_fragment_size]
        encoded_fragments[i] = encode_message(flags_types['FLAG_MSG_FRAG'], i, window_size, fragment)
    #while first non delivered fragment is not one after last fragment
    while sf <= last_fragment_number:
        #send fragments from the window
        for i in range(sf, min(sf + window_size, last_fragment_number + 1)):
            if not ack_fragments[i] and i >= sf:
                send_sock.sendto(encoded_fragments[i], (peer_ip, peer_port))
                thread_safe_print(f"sent fragment\t\t\t\t{i}")
            #check if peer is getting ack
            present_time = time.time()
            #if no ack delivered in last 5 seconds send keepalive
            if present_time - last_msg > 5:
                thread_safe_print("\nInactivity detected, sending keep-alive.\n")
                ack_received = False
                tries = 0
                #try 3 times
                while not ack_received and tries < 3:
                    encoded_msg = encode_message(flags_types['FLAG_KEEPALIVE'], 0, 0, "")
                    thread_safe_print("sent KEEPALIVE")
                    send_sock.sendto(encoded_msg, (peer_ip, peer_port))
                    wait = 0
                    #wait for response for 5 seconds, then try again
                    while not ack_received and wait < 5:
                        time.sleep(0.1)
                        wait += 0.1
                    tries += 1
                #if no ack delivered peer disconnected
                if not ack_received:
                    update_output_text("Disconnected")
                    connected = False
                    update_status_info()
                    return
    try:
        #if there are messages to print, finish printing
        while not message_queue.empty():
            message = message_queue.get_nowait()
            print(message)
    except queue.Empty:
        pass
    #message delivered
    thread_safe_print("\nMessage delivered\n")


def receive_msg_ack_and_req(last_fragment_number):
    global requested_fragments,sf, fragment_lock, ack_received, last_msg, tries
    sf = 0
    last_msg = time.time()
    #while first non delivered fragment is not fragment after last fragment
    while sf<last_fragment_number+1 and connected and running:
        try:
            data, addr = rec_sock.recvfrom(1500)
            msg = decode_message(data)
            last_msg = time.time()
            #if request encode new message and send
            if msg['flags'] == flags_types['FLAG_MSG_REQ']:
                if msg['fragment_number'] == last_fragment_number:
                    fragment = message[msg['fragment_number'] * max_fragment_size:]
                else:
                    fragment = message[msg['fragment_number'] * max_fragment_size:(msg[
                                                                                       'fragment_number'] + 1) * max_fragment_size]
                encoded_fragments[msg['fragment_number']] = encode_message(flags_types['FLAG_MSG_FRAG'],
                                                                           msg['fragment_number'], 0, fragment)
                send_sock.sendto(encoded_fragments[msg['fragment_number']], (peer_ip, peer_port))
                thread_safe_print(
                    f"received fragment REQ\t\t{msg['fragment_number']}\nsent fragment\t\t\t\t{msg['fragment_number']}")
            #when ack update sf and update ack info
            elif msg['flags'] == flags_types['FLAG_MSG_ACK']:
                thread_safe_print(f"received fragment ACK\t\t{msg['fragment_number']}")
                sf = max(msg['fragment_number'] + 1, sf)
                for i in range(0, sf):
                    if sf < last_fragment_number + 1:
                        ack_fragments[i] = True
            #if received keepalive send keepalive ack
            elif msg['flags'] == flags_types['FLAG_KEEPALIVE']:
                thread_safe_print("received KEEPALIVE")
                ack_msg = encode_message(flags_types['FLAG_KEEPALIVE_ACK'], 0, 0, "")
                send_sock.sendto(ack_msg, (peer_ip, peer_port))
                thread_safe_print("sent KEEPALIVE_ACK")
            #if received keepalive ack, confirmed connection
            elif msg['flags'] == flags_types['FLAG_KEEPALIVE_ACK']:
                thread_safe_print("received KEEPALIVE_ACK")
                ack_received = True
                tries = 0
        except socket.timeout:
            continue
        except OSError:
            continue


def receive_message(last_fragment_number):
    global sending, connected, wait, delivered_keepalive
    last_msg = time.time()
    received_set = {}
    #next fragment to save
    rn = 0
    min_rn_req = -1
    timeout = 0
    complete_msg = ""
    #while last fragment isn't saved
    while rn <= last_fragment_number:
        try:
            rec_sock.settimeout(5)
            data, addr = rec_sock.recvfrom(1500)
            msg = decode_message(data)
            last_msg = time.time()
            if not connected:
                return
            last_msg = time.time()
            #if keepalive received send keepalive ack
            if msg['flags'] == flags_types['FLAG_KEEPALIVE']:
                thread_safe_print("received KEEPALIVE")
                ack_msg = encode_message(flags_types['FLAG_KEEPALIVE_ACK'], 0, 0, "")
                send_sock.sendto(ack_msg, (peer_ip, peer_port))
                thread_safe_print("sent KEEPALIVE_ACK")
            #if keepalive ack received confirmed connection
            elif msg['flags'] == flags_types['FLAG_KEEPALIVE_ACK']:
                thread_safe_print("received KEEPALIVE_ACK")
                sending = True
                delivered_keepalive = True
            #fragment is already saved
            elif msg['fragment_number'] < rn:
                continue
            #if message correct
            elif msg['checksum'] == get_checksum(msg['data']):
                frag_num = msg['fragment_number']
                received_set[frag_num] = msg['data']
                #if next fragment is in set start saving and send ack
                if rn in received_set:
                    while rn in received_set:
                        complete_msg += received_set[rn].decode('utf-8')
                        rn += 1
                    encoded_msg = encode_message(flags_types['FLAG_MSG_ACK'], rn - 1, 0, b'')
                    send_sock.sendto(encoded_msg, (peer_ip, peer_port))
                    print(f"received fragment\t\t\t<-{msg['fragment_number']}✔\nsent fragment ACK\t\t\t->{rn - 1}")
                #if out of order send request if it wasn't send, after 15 other messages received resend
                elif min_rn_req < rn or timeout > 15:
                    encoded_msg = encode_message(flags_types['FLAG_MSG_REQ'], rn, 0, b'')
                    send_sock.sendto(encoded_msg, (peer_ip, peer_port))
                    print(f"received fragment\t\t\t<-{msg['fragment_number']}✔\nsent fragment REQ\t\t\t->{rn}")
                    min_rn_req = rn
                    timeout = 0
                else:
                    print(f"received fragment\t\t\t<-{msg['fragment_number']}✔")
                    timeout += 1
            #message corrupted
            else:
                encoded_msg = encode_message(flags_types['FLAG_MSG_REQ'], msg['fragment_number'], 0, b'')
                send_sock.sendto(encoded_msg, (peer_ip, peer_port))
                print(
                    f"received corrupt fragment\t<-{msg['fragment_number']}✘\nsent fragment REQ\t\t\t->{msg['fragment_number']}")
        except socket.timeout:
            #after 5 seconds of no messages try connection
            present_time = time.time()
            if present_time - last_msg > 5:
                thread_safe_print("\nInactivity detected, sending keep-alive.\n")
                signal = False
                tries = 3
                while not signal and tries > 0:
                    keepalive_msg = encode_message(flags_types['FLAG_KEEPALIVE'], 0, 0, "")
                    send_sock.sendto(keepalive_msg, (peer_ip, peer_port))
                    thread_safe_print("sent KEEPALIVE")
                    rec_sock.settimeout(5)
                    try:
                        data, addr = rec_sock.recvfrom(1500)
                        msg = decode_message(data)
                        #if received keepalive ack connection confirmed
                        if msg['flags'] == flags_types['FLAG_KEEPALIVE_ACK']:
                            signal = True
                            break
                        #if keepalive received send ack
                        elif msg['flags'] == flags_types['FLAG_KEEPALIVE']:
                            thread_safe_print("received KEEPALIVE")
                            ack_msg = encode_message(flags_types['FLAG_KEEPALIVE_ACK'], 0, 0, "")
                            send_sock.sendto(ack_msg, (peer_ip, peer_port))
                            thread_safe_print("sent KEEPALIVE_ACK")
                            signal = True
                            break
                    except socket.timeout:
                        tries -= 1
                #if no ack delivered disconnected
                if not signal:
                    connected = False
                    update_status_info()
                    update_output_text("Disconnected")
                    rec_sock.settimeout(0.1)
                    return
        except OSError:
            continue
    rec_sock.settimeout(0.1)
    #message delivered
    update_output_text(f"Peer: {complete_msg}")
    thread_safe_print(f"Size of text: {len(complete_msg)}")


########################################################################################################################
# send file
def send_file_parameters():
    global sending, delivered, requested
    delivered = False
    requested = False
    file_path = file_entry.get()
    if os.path.isfile(file_path) and connected:
        sending = True
        update_status_info()
        file_name = os.path.basename(file_path)
        with open(file_path, 'rb') as file:
            file_content = file.read()
        last_fragment = len(file_content) // max_fragment_size
        # window size should be less than half of fragment number
        if last_fragment / 2 >= 65535:
            window_size = 65535
        else:
            window_size = last_fragment // 2
            if window_size == 0:
                window_size = 1
        encoded_msg = encode_message(flags_types['FLAG_DATA_PAR'], last_fragment, window_size, file_name)
        send_sock.sendto(encoded_msg, (peer_ip, peer_port))
        # information about transfer
        thread_safe_print(f"\nreceived DATA PAR:")
        thread_safe_print(f"Last fragment number: {last_fragment}")
        thread_safe_print(f"Number of fragments: {last_fragment + 1}")
        thread_safe_print(f"Max window size: {window_size}")
        thread_safe_print(f"Size of file: {len(file_content)}B")
        thread_safe_print(f"Fragment size: {max_fragment_size}")
        # if last fragment has different size, the size is printed
        if len(file_content[last_fragment * max_fragment_size:]) != max_fragment_size:
            thread_safe_print(f"Last fragment size: {len(file_content[last_fragment * max_fragment_size:])}")
        thread_safe_print(f"File path: {file_path}\n")
        # check for delivery
        root.after(500, lambda: check_file_parameters(3, last_fragment, window_size, file_name))


def check_file_parameters(remaining_tries, last_fragment, window_size, file_name):
    global connected
    if connected:
        # if requested send again
        if requested:
            encoded_msg = encode_message(flags_types['FLAG_DATA_PAR'], last_fragment, window_size, file_name)
            send_sock.sendto(encoded_msg, (peer_ip, peer_port))
            thread_safe_print(f"Sent DATA_PAR")
            root.after(500, lambda: check_file_parameters(remaining_tries, last_fragment, window_size, file_name))
        # if not delivered try again or status is disconnected
        elif not delivered:
            if remaining_tries > 1:
                thread_safe_print(f"\nUnable to reach, remaining tries:{remaining_tries - 1}\n")
                encoded_msg = encode_message(flags_types['FLAG_DATA_PAR'], last_fragment, window_size, file_name)
                send_sock.sendto(encoded_msg, (peer_ip, peer_port))
                thread_safe_print(f"Sent DATA_PAR")
                root.after(500,
                           lambda: check_file_parameters(remaining_tries - 1, last_fragment, window_size, file_name))
            else:
                update_output_text("Data not delivered")
                update_output_text("Peer not reached")
                connected = False
                update_status_info()
        # if delivered start sending
        elif delivered:
            send_file(last_fragment, window_size)


def send_file(last_fragment_number, window_size):
    global sf, requested_fragments,fragment_lock, ack_fragments, encoded_fragments, file_content, ack_received, connected, tries

    file_path = file_entry.get()
    #read file content once
    with open(file_path, 'rb') as file:
        file_content = file.read()
    # first fragment not delivered
    sf = 0
    encoded_fragments = {}
    requested_fragments = queue.Queue()
    # info about fragments delivery
    ack_fragments = [False] * (last_fragment_number + 1)
    # encoding messages
    for i in range(last_fragment_number + 1):
        if i == last_fragment_number:
            fragment = file_content[i * max_fragment_size:]
        else:
            fragment = file_content[i * max_fragment_size:(i + 1) * max_fragment_size]
        encoded_fragments[i] = encode_message(flags_types['FLAG_DATA'], i, window_size, fragment)
    # while first non delivered fragment is not one after last fragment
    while sf <= last_fragment_number:
        # send fragments from the window
        for i in range(sf, min(sf + window_size, last_fragment_number + 1)):
            if not ack_fragments[i] and i >= sf:
                send_sock.sendto(encoded_fragments[i], (peer_ip, peer_port))
                thread_safe_print(f"sent fragment\t\t\t\t{i}")
            # check if peer is getting ack
            present_time = time.time()
            # if no ack delivered in last 5 seconds send keepalive
            if present_time - last_msg > 5:
                thread_safe_print("\nInactivity detected, sending keep-alive.\n")
                ack_received = False
                tries = 0
                # try 3 times
                while not ack_received and tries < 3:
                    encoded_msg = encode_message(flags_types['FLAG_KEEPALIVE'], 0, 0, "")
                    thread_safe_print("sent KEEPALIVE")
                    send_sock.sendto(encoded_msg, (peer_ip, peer_port))
                    wait = 0
                    # wait for response for 5 seconds, then try again
                    while not ack_received and wait < 5:
                        time.sleep(0.1)
                        wait += 0.1
                    tries += 1
                # if no ack delivered peer disconnected
                if not ack_received:
                    connected = False
                    update_output_text("Disconnected")
                    update_status_info()
                    return
    try:
        # if there are messages to print, finish printing
        while not message_queue.empty():
            message = message_queue.get_nowait()
            print(message)
    except queue.Empty:
        pass
    # file delivered
    thread_safe_print("\nFile delivered\n")
    update_output_text(f"You: send file-> {file_path}")


def receive_file_ack_and_req(last_fragment_number):
    global requested_fragments, sf, fragment_lock, ack_received, last_msg, tries
    sf = 0
    last_msg = time.time()
    # while first non delivered fragment is not fragment after last fragment
    while sf<last_fragment_number+1 and connected and running:
        try:
            data, addr = rec_sock.recvfrom(1500)
            msg = decode_message(data)
            last_msg = time.time()
            # if request encode new message and send
            if msg['flags'] == flags_types['FLAG_DATA_REQ']:
                if msg['fragment_number'] == last_fragment_number:
                    fragment = file_content[msg['fragment_number'] * max_fragment_size:]
                else:
                    fragment = file_content[msg['fragment_number'] * max_fragment_size:(msg[
                                                                                            'fragment_number'] + 1) * max_fragment_size]
                encoded_fragments[msg['fragment_number']] = encode_message(flags_types['FLAG_DATA'],
                                                                           msg['fragment_number'], 0, fragment)
                send_sock.sendto(encoded_fragments[msg['fragment_number']], (peer_ip, peer_port))
                thread_safe_print(
                    f"received fragment REQ\t\t{msg['fragment_number']}\nsent fragment\t\t\t\t{msg['fragment_number']}")
            # when ack update sf and update ack info
            elif msg['flags'] == flags_types['FLAG_DATA_ACK']:
                thread_safe_print(f"received fragment ACK\t\t{msg['fragment_number']}")
                sf = max(msg['fragment_number'] + 1, sf)
                for i in range(0, sf):
                    if sf < last_fragment_number + 1:
                        ack_fragments[i] = True
            # if received keepalive send keepalive ack
            elif msg['flags'] == flags_types['FLAG_KEEPALIVE']:
                thread_safe_print("received KEEPALIVE")
                ack_msg = encode_message(flags_types['FLAG_KEEPALIVE_ACK'], 0, 0, "")
                send_sock.sendto(ack_msg, (peer_ip, peer_port))
                thread_safe_print("sent KEEPALIVE_ACK")
            # if received keepalive ack, confirmed connection
            elif msg['flags'] == flags_types['FLAG_KEEPALIVE_ACK']:
                thread_safe_print("received KEEPALIVE_ACK")
                ack_received = True
                tries = 0
        except socket.timeout:
            continue
        except OSError:
            continue


def receive_file(name, last_fragment_number, window_size):
    global sending, connected, wait, delivered_keepalive
    last_msg = time.time()
    received_set = {}
    # next fragment to save
    rn = 0
    min_rn_req = -1
    #join address and name
    if download_address[-1] == "\\":
        address = download_address + name
    else:
        address = download_address + "\\" + name
    print(f"\nSaving file to {address}\n")
    timeout = 0
    # while last fragment isn't saved
    with open(address, 'wb') as file:
        while rn <= last_fragment_number:
            try:
                rec_sock.settimeout(5)
                data, addr = rec_sock.recvfrom(1500)
                msg = decode_message(data)
                last_msg = time.time()
                # if keepalive received send keepalive ack
                if msg['flags'] == flags_types['FLAG_KEEPALIVE']:
                    thread_safe_print("received KEEPALIVE")
                    ack_msg = encode_message(flags_types['FLAG_KEEPALIVE_ACK'], 0, 0, "")
                    send_sock.sendto(ack_msg, (peer_ip, peer_port))
                    thread_safe_print("sent KEEPALIVE_ACK")
                # if keepalive ack received confirmed connection
                elif msg['flags'] == flags_types['FLAG_KEEPALIVE_ACK']:
                    thread_safe_print("received KEEPALIVE_ACK")
                    sending = True
                    delivered_keepalive = True
                #fragment is already saved
                elif msg['fragment_number'] < rn:
                    continue
                # if message correct
                elif msg['checksum'] == get_checksum(msg['data']):
                    frag_num = msg['fragment_number']
                    received_set[frag_num] = msg['data']
                    # if next fragment is in set start saving and send ack
                    if rn in received_set:
                        while rn in received_set:
                            file.write(received_set[rn])
                            rn += 1
                        encoded_msg = encode_message(flags_types['FLAG_DATA_ACK'], rn - 1, 0, b'')
                        send_sock.sendto(encoded_msg, (peer_ip, peer_port))
                        print(f"received fragment\t\t\t<-{frag_num}✔\nsent fragment ACK\t\t\t->{rn - 1}")
                    # if out of order send request if it wasn't send, after 15 other messages received resend
                    elif min_rn_req < rn or timeout > 15:
                        encoded_msg = encode_message(flags_types['FLAG_DATA_REQ'], rn, 0, b'')
                        send_sock.sendto(encoded_msg, (peer_ip, peer_port))
                        print(f"received fragment\t\t\t<-{frag_num}✔\nsent fragment REQ\t\t\t->{rn}")
                        min_rn_req = rn
                        timeout = 0
                    else:
                        print(f"received fragment\t\t\t<-{frag_num}✔")
                        timeout += 1
                # message corrupted
                else:
                    encoded_msg = encode_message(flags_types['FLAG_DATA_REQ'], msg['fragment_number'], 0, b'')
                    send_sock.sendto(encoded_msg, (peer_ip, peer_port))
                    print(f"received corrupt fragment\t<-{msg['fragment_number']}✘\nsent fragment REQ\t\t\t->{msg['fragment_number']}")
            except socket.timeout:
                # after 5 seconds of no messages try connection
                present_time = time.time()
                if present_time - last_msg > 5:
                    thread_safe_print("\nInactivity detected, sending keep-alive.\n")
                    signal = False
                    tries = 3
                    while not signal and tries > 0:
                        keepalive_msg = encode_message(flags_types['FLAG_KEEPALIVE'], 0, 0, "")
                        send_sock.sendto(keepalive_msg, (peer_ip, peer_port))
                        thread_safe_print("sent KEEPALIVE")
                        rec_sock.settimeout(5)
                        try:
                            data, addr = rec_sock.recvfrom(1500)
                            msg = decode_message(data)
                            # if received keepalive ack connection confirmed
                            if msg['flags'] == flags_types['FLAG_KEEPALIVE_ACK']:
                                thread_safe_print("received KEEPALIVE_ACK during inactivity")
                                signal = True
                                break
                            # if keepalive received send ack
                            elif msg['flags'] == flags_types['FLAG_KEEPALIVE']:
                                thread_safe_print("received KEEPALIVE")
                                ack_msg = encode_message(flags_types['FLAG_KEEPALIVE_ACK'], 0, 0, "")
                                send_sock.sendto(ack_msg, (peer_ip, peer_port))
                                thread_safe_print("sent KEEPALIVE_ACK")
                                signal = True
                                break
                        except socket.timeout:
                            tries -= 1
                    # if no ack delivered disconnected
                    if not signal:
                        connected = False
                        update_output_text("Disconnected")
                        update_status_info()
                        rec_sock.settimeout(0.1)
                        return
            except OSError:
                continue
    rec_sock.settimeout(0.1)
    update_output_text(f"Peer: send file-> {address}")
    #file delivered
    print("\nFile successfully saved.")
    print("Size of file", os.path.getsize(address))
    print("Size of file", address)


#clear socket
def clear_socket_buffer(sock):
    try:
        while True:
            data, addr = sock.recvfrom(1500)  # Adjust buffer size as needed
    except socket.timeout:
        pass
    except OSError as e:
        pass
    finally:
        pass


########################################################################################################################
# receive thread
def receive():
    global connected, delivered, sending, delivered_keepalive, wait, requested, last_keepalive_sent, last_keepalive_ack
    while running:
        try:
            data, addr = rec_sock.recvfrom(1500)
            msg = decode_message(data)
            #settings are configured delivery is possible
            if setting:
                #if HS1 received send HS2
                if msg['flags'] == flags_types['FLAG_HS1'] and msg['checksum'] == get_checksum(msg['data']):
                    thread_safe_print("received HS1")
                    encoded_msg = encode_message(flags_types['FLAG_HS2'], 0, 0, "")
                    send_sock.sendto(encoded_msg, (peer_ip, peer_port))
                    thread_safe_print("sent HS2")
                #if HS2 received send HS3
                elif msg['flags'] == flags_types['FLAG_HS2'] and msg['checksum'] == get_checksum(msg['data']):
                    thread_safe_print("received HS2")
                    encoded_msg = encode_message(flags_types['FLAG_HS3'], 0, 0, "")
                    send_sock.sendto(encoded_msg, (peer_ip, peer_port))
                    thread_safe_print("sent HS3")
                    #connected and not sending
                    connected = True
                    sending = False
                    last_keepalive_sent = 0
                    last_keepalive_ack = 0
                    update_status_info()
                #if HS3 received
                elif msg['flags'] == flags_types['FLAG_HS3'] and msg['checksum'] == get_checksum(msg['data']):
                    thread_safe_print("received HS3")
                    #connected and not sending
                    connected = True
                    sending = False
                    last_keepalive_sent = 0
                    last_keepalive_ack = 0
                    thread_safe_print("\nConnected\n")
                    update_status_info()
                #if connected delivery of files, text and keepalive is possible
                if connected:
                    #if msg parameters delivered send ack and print info
                    if msg['flags'] == flags_types['FLAG_MSG_PAR']:
                        sending = True
                        update_status_info()
                        if msg['checksum'] == get_checksum(msg['data']):
                            start_time = time.time()
                            thread_safe_print(f"\nreceived MSG PAR:")
                            thread_safe_print(f"Last fragment number: {msg['fragment_number']}")
                            thread_safe_print(f"Max window size: {msg['window_size']}\n")
                            ack_msg = encode_message(flags_types['FLAG_MSG_PAR_ACK'], msg['fragment_number'],
                                                     msg['window_size'], "")
                            send_sock.sendto(ack_msg, (peer_ip, peer_port))
                            thread_safe_print("sent MSG_PAR_ACK\n")
                            #start receiving message
                            receive_message(msg['fragment_number'])
                            #if connected delivery successful
                            if connected:
                                sending = False
                                update_status_info()
                                end_time = time.time()
                                print(f"\nMessage delivered\nTime: {end_time - start_time}\n")
                                clear_socket_buffer(rec_sock)
                                clear_socket_buffer(send_sock)
                        #corrupted msg parameters send request
                        else:
                            thread_safe_print("received fault MSG_PAR")
                            ack_msg = encode_message(flags_types['FLAG_MSG_PAR_REQ'], 0, 0, "")
                            send_sock.sendto(ack_msg, (peer_ip, peer_port))
                            thread_safe_print("sent MSG_PAR_REQ")
                            sending = False
                            update_status_info()
                    #if message ack received start receiving msg ack
                    elif msg['flags'] == flags_types['FLAG_MSG_PAR_ACK'] and msg['checksum'] == get_checksum(
                            msg['data']):
                        thread_safe_print("received MSG_PAR_ACK\n")
                        delivered = True
                        requested = False
                        sending = True
                        update_status_info()
                        receive_msg_ack_and_req(msg['fragment_number'])
                        #if connected text delivery successful
                        if connected:
                            sending = False
                            update_status_info()
                            update_output_text(f"You: {text}")
                            clear_socket_buffer(rec_sock)
                            clear_socket_buffer(send_sock)
                    #if msg parameters request resend
                    elif msg['flags'] == flags_types['FLAG_MSG_PAR_REQ'] and msg['checksum'] == get_checksum(
                            msg['data']):
                        thread_safe_print("received MSG_PAR_REQ")
                        requested = True
                    #if received msg
                    elif msg['flags'] == flags_types['FLAG_MSG']:
                        #if correct print content
                        if msg['checksum'] == get_checksum(msg['data']):
                            thread_safe_print(f"\nreceived MSG: {msg['data'].decode('utf-8')}")
                            update_output_text(f"Peer: {msg['data'].decode('utf-8')}")
                            ack_msg = encode_message(flags_types['FLAG_MSG_ACK'], 0, 0, "")
                            send_sock.sendto(ack_msg, (peer_ip, peer_port))
                            thread_safe_print("sent MSG_ACK\n")
                        #if corrupted, request
                        else:
                            thread_safe_print("received fault MSG")
                            ack_msg = encode_message(flags_types['FLAG_MSG_REQ'], 0, 0, "")
                            send_sock.sendto(ack_msg, (peer_ip, peer_port))
                            thread_safe_print("sent MSG_REQ")
                    #if msg ack, end sending process
                    elif msg['flags'] == flags_types['FLAG_MSG_ACK'] and msg['checksum'] == get_checksum(msg['data']):
                        thread_safe_print("received MSG_ACK\n")
                        delivered = True
                        requested = False
                        sending = False
                        update_status_info()
                        update_output_text(f"You: {text}")
                    #if msg request, resend
                    elif msg['flags'] == flags_types['FLAG_MSG_REQ'] and msg['checksum'] == get_checksum(msg['data']):
                        thread_safe_print("received MSG_REQ")
                        requested = True
                    #received file parameters
                    elif msg['flags'] == flags_types['FLAG_DATA_PAR']:
                        sending = True
                        update_status_info()
                        #if correct print info and start receiving
                        if msg['checksum'] == get_checksum(msg['data']):
                            start_time = time.time()
                            thread_safe_print(f"\nreceived File Parameters:")
                            thread_safe_print(f"Last fragment number: {msg['fragment_number']}")
                            thread_safe_print(f"Max window size: {msg['window_size']}")
                            thread_safe_print(f"File name: {msg['data']}\n")
                            ack_msg = encode_message(flags_types['FLAG_DATA_PAR_ACK'], msg['fragment_number'],
                                                     msg['window_size'], "")
                            send_sock.sendto(ack_msg, (peer_ip, peer_port))
                            thread_safe_print("sent DATA_PAR_ACK")
                            receive_file(msg['data'].decode(), msg['fragment_number'], msg['window_size'])
                            #if connected delivery successful
                            if connected:
                                sending = False
                                update_status_info()
                                end_time = time.time()
                                print(f"\nTime: {end_time - start_time}\n")
                                clear_socket_buffer(rec_sock)
                                clear_socket_buffer(send_sock)
                        #if corrupted, request
                        else:
                            thread_safe_print("received fault DATA_PAR")
                            ack_msg = encode_message(flags_types['FLAG_DATA_PAR_REQ'], 0, 0, "")
                            send_sock.sendto(ack_msg, (peer_ip, peer_port))
                            thread_safe_print("sent DATA_PAR_REQ")
                            sending = False
                            update_status_info()
                    #if file parameters ack, start receiving ack and req
                    elif msg['flags'] == flags_types['FLAG_DATA_PAR_ACK'] and msg['checksum'] == get_checksum(
                            msg['data']):
                        thread_safe_print("received DATA_PAR_ACK\n")
                        delivered = True
                        requested = False
                        sending = True
                        update_status_info()
                        receive_file_ack_and_req(msg['fragment_number'])
                        if connected:
                            sending = False
                            update_status_info()
                            clear_socket_buffer(rec_sock)
                            clear_socket_buffer(send_sock)
                    #if file parameters req, resend
                    elif msg['flags'] == flags_types['FLAG_DATA_PAR_REQ'] and msg['checksum'] == get_checksum(
                            msg['data']):
                        thread_safe_print("received DATA_PAR_REQ")
                        requested = True
                    #if exit received, disconnected and send exit ack
                    elif msg['flags'] == flags_types['FLAG_EXIT'] and msg['checksum'] == get_checksum(msg['data']):
                        thread_safe_print("\nreceived EXIT")
                        ack_msg = encode_message(flags_types['FLAG_EXIT_ACK'], 0, 0, "")
                        send_sock.sendto(ack_msg, (peer_ip, peer_port))
                        thread_safe_print("sent EXIT_ack")
                        connected = False
                        update_status_info()
                    #if exit ack delivered, disconnected
                    elif msg['flags'] == flags_types['FLAG_EXIT_ACK'] and msg['checksum'] == get_checksum(msg['data']):
                        thread_safe_print("received EXIT_ACK")
                        connected = False
                        sending = False
                        update_status_info()
                    #if keepalive received send keepalive ack
                    elif msg['flags'] == flags_types['FLAG_KEEPALIVE'] and msg['checksum'] == get_checksum(msg['data']):
                        thread_safe_print("received KEEPALIVE")
                        ack_msg = encode_message(flags_types['FLAG_KEEPALIVE_ACK'], 0, 0, "")
                        send_sock.sendto(ack_msg, (peer_ip, peer_port))
                        thread_safe_print("sent KEEPALIVE_ACK")
                        connected = True
                    #if keepalive ack delivered
                    elif msg['flags'] == flags_types['FLAG_KEEPALIVE_ACK'] and msg['checksum'] == get_checksum(
                            msg['data']):
                        thread_safe_print("received KEEPALIVE_ACK")
                        delivered_keepalive = True
        except socket.timeout:
            continue
        except OSError:
            continue


########################################################################################################################
# canvas

#updating msg box with new text
def update_output_text(msg):
    global output_text
    output_text.config(state=tk.NORMAL)
    output_text.insert(tk.END, msg + "\n")
    output_text.config(state=tk.DISABLED)

#show settings window
def show_settings_canvas():
    canvas.pack_forget()
    settings_canvas.pack()

#hide settings window and save options
def hide_settings_canvas():
    global download_address, max_fragment_size, connect_button, setting, corruption_rate
    download_address = download_entry.get()
    max_fragment_size = fragment_entry.get()
    corruption_rate = corruption_entry.get()
    right = True
    #test parametres
    try:
        max_fragment_size = int(max_fragment_size)
        corruption_rate = float(corruption_rate)
        if not 0 <= corruption_rate <= 50:
            right = False
        #maximum is 1449 so total msg is no longer than 1500
        if not 1 <= max_fragment_size <= 1449:
            right = False
        if not os.path.isdir(download_address):
            right = False
    except ValueError:
        right = False
    #if right parameters hide window and able to connect
    if right:
        settings_canvas.pack_forget()
        canvas.pack()
        thread_safe_print(
            f"\nDownload address: {download_address}\nMax fragment size: {max_fragment_size}\nCorruption rate: {corruption_rate}%\n")
        update_output_text("Settings updated")
        connect_button.config(state="normal")
        setting = True

#GUI
def setup_gui():
    global root, output_text, message_entry, file_entry, status_label, canvas, settings_canvas, download_entry, fragment_entry, connect_button, disconnect_button, message_button, message_entry, file_button, file_entry, corruption_entry, settings_button
    root = tk.Tk()
    root.title("Peer")
    #canvas
    canvas = tk.Canvas(root, width=790, height=350)
    canvas.pack()
    #connect
    connect_button = tk.Button(root, text="Connect", command=lambda: send_HS1(3), state=tk.DISABLED)
    connect_button.place(x=22, y=20)
    #disconnect
    disconnect_button = tk.Button(root, text="Disconnect", command=lambda: send_EXIT(3), state=tk.DISABLED)
    disconnect_button.place(x=100, y=20)
    #status
    status_label = tk.Label(root, text="Disconnected", fg="red")
    status_label.place(x=245, y=20)
    #message
    message_label = tk.Label(root, text="Enter text of the message")
    message_label.place(x=20, y=79)
    message_entry = tk.Entry(root, width=50, state=tk.DISABLED)
    message_entry.place(x=22, y=100)
    message_button = tk.Button(root, text="Send Message", command=lambda: send_message(3), state=tk.DISABLED)
    message_button.place(x=20, y=122)
    #file
    file_label = tk.Label(root, text="Enter the address of the file")
    file_label.place(x=20, y=159)
    file_entry = tk.Entry(root, width=50, state=tk.DISABLED)
    file_entry.place(x=22, y=180)
    file_button = tk.Button(root, text="Send File", command=send_file_parameters, state=tk.DISABLED)
    file_button.place(x=20, y=202)
    #settings
    settings_button = tk.Button(root, text="Settings", command=show_settings_canvas)
    settings_button.place(x=20, y=302)
    #output window
    frame = tk.Frame(root)
    frame.place(x=350, y=20)
    output_text = tk.Text(frame, height=19, width=50, wrap="word", state=tk.DISABLED)
    output_text.grid(row=0, column=0)
    scrollbar = tk.Scrollbar(frame, orient="vertical", command=output_text.yview)
    scrollbar.grid(row=0, column=1, sticky="ns")
    output_text.config(yscrollcommand=scrollbar.set)
    #settings canvas
    settings_canvas = tk.Canvas(root, width=350, height=350)
    #download option
    download_label = tk.Label(settings_canvas, text="Enter download address")
    download_label.place(x=20, y=20)
    download_entry = tk.Entry(settings_canvas, width=50)
    download_entry.insert(0, "C:\\Users\\maria\\OneDrive\\Desktop\\ZS-2024\\PKS\\Kontrolny bod")
    download_entry.place(x=22, y=41)
    #fragment size
    fragment_label = tk.Label(settings_canvas, text="Enter fragment size(1-1449B)")
    fragment_label.place(x=20, y=70)
    fragment_entry = tk.Entry(settings_canvas, width=50)
    fragment_entry.insert(0, "1")
    fragment_entry.place(x=22, y=91)
    #corruption rate
    corruption_label = tk.Label(settings_canvas, text="Enter rate of data corruption(0-50%)")
    corruption_label.place(x=20, y=120)
    corruption_entry = tk.Entry(settings_canvas, width=50)
    corruption_entry.insert(0, "0")
    corruption_entry.place(x=22, y=141)
    #save and hide settings window
    save_button = tk.Button(settings_canvas, text="Save", command=hide_settings_canvas)
    save_button.place(x=20, y=302)
    settings_canvas.pack_forget()

    update_output_text("Before usage configurate settings.")
    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()

#when closed, close sockets and end root
def on_close():
    global running
    running = False
    send_sock.close()
    rec_sock.close()
    root.destroy()


########################################################################################################################
# start of program

#input
local_ip = input("Your IP address: ")
local_port = int(input("Your listening port: "))
peer_ip = input("Peer's IP address: ")
peer_port = int(input("Peer's listening port: "))

#socket initialization
rec_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
send_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
rec_sock.bind((local_ip, local_port))
rec_sock.settimeout(0.1)
rec_sock.setblocking(False)
send_sock.setblocking(False)
#increased buffer to avoid message lose
rec_sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 8 * 1024 * 1024)
send_sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 8 * 1024 * 1024)
#thread initialization
threading.Thread(target=receive, daemon=True).start()
threading.Thread(target=keep_alive, daemon=True).start()
#gui setup
setup_gui()
