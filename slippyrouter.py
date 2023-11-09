import logging
import serial
import socket
import threading
import time
import base64
import json

TCP_PORT = 3006
SERIAL_PORT = "COM11"
SERIAL_BUAD = 115200

ser = serial.Serial(SERIAL_PORT, SERIAL_BUAD)

client_sockets = []

LOCAL_ADDRESS = 0x00000000

# JSON API
#
# slippy::send -> Send data over slippymesh. args: <to (0x01234567)> <type (0-255)> <service (0-255)> <flags ([false,true,...])> <data (Base64 String)>
# slippy::recive <- Called when data was recived from slippymesh. return-args: <to (0x01234567)> <from (0x01234567)> <type (0-255)> <service (0-255)> <flags ([false,true,...])> <uid (0x01234567)> <size (int)> <data (Base64 String)> <rssi (int)> <snr (int)>
#
# slippy::get_info <-> Get some basic info about the device. return-args: <address (0x01234567)>
#
# serial::send -> Send data to the raw serial port. args: <data (UTF-8 String)> Max 512 bytes
# serial::recive <- Called when data was recived from the raw serial port. return-args: <data (UTF-8 String)>
# serial::reset -> Reset the serial device.
#
# eg: {"function":"...", "args":{"...":"..."}}

def serial_reader():
    while True:
        data = ser.readline()
        if data:
            message = data.decode()

            slippy_recive = None
            serial_recive = json.dumps({
                "function": "serial::recive",
                "args": {
                    "data": message
                }
            }).encode()
            if (message[:16] == "Your address is:"):
                LOCAL_ADDRESS = message[17:]
            elif (message[:5] == "JSON:"):
                obj = json.loads(message[6:])
                slippy_recive = json.dumps({
                    "function": "slippy::recive",
                    "args": {
                        "to": str(obj["to"]),
                        "from": str(obj["from"]),
                        "service": int(obj["service"]),
                        "type": int(obj["type"]),
                        "flags": obj["flags"],
                        "uid": str(obj["uid"]),
                        "size": int(obj["size"]),
                        "data": str(obj["data"]),
                        "rssi": int(obj["rssi"]),
                        "snr": int(obj["snr"]),
                    }
                }).encode()
            for client_socket in client_sockets:

                client_socket.send(serial_recive+b'\n')

                if (slippy_recive != None):
                    client_socket.send(slippy_recive+b'\n')



def handle_client(client_socket, addr):
    try:
        while True:
            data = client_socket.recv(2048)
            if not data:
                break
            
            obj = json.loads(str(data.decode()))

            if (str(obj["function"]) == "serial::send"): # Send data to serial
                message = str(obj["args"]["data"])

                ser.write(message.encode())
                
            elif (str(obj["function"]) == "serial::reset"): # Reset the serial device
                ser.close()
                time.sleep(1)
                ser.open()
            
            elif (str(obj["function"]) == "slippy::send"): # Send a message to slippymesh
                _to = str(obj["args"]["to"])
                _data = str(obj["args"]["data"])
                _type = int(obj["args"]["type"])
                _service = int(obj["args"]["service"])
                _flags = obj["args"]["flags"]

                _flags_string = ''.join('1' if b else '0' for b in _flags)

                ser.write(f"send64 {_to} \"{_data}\" {_type} {_service} 0b{_flags_string}\n".encode())

            elif (str(obj["function"]) == "slippy::get_info"): # Get basic infomation
                res = json.dumps({
                    "function": "slippy::get_info",
                    "args": {
                        "address": str(LOCAL_ADDRESS),
                    }
                })

                client_socket.send(json.dumps(res).encode())
                
    except ConnectionResetError:
        pass

    finally:
        logging.info(f"{addr[0]}:{addr[1]} Dissconnected")
        client_socket.close()
        client_sockets.remove(client_socket)


def handle_server(server):
    while True:
        client, addr = server.accept()
        logging.info(f"Accepted connection from {addr[0]}:{addr[1]}")
        client_sockets.append(client)
        
        client_handler = threading.Thread(target=handle_client, daemon=True, args=(client, addr,))
        client_handler.start()

if __name__ == "__main__":
    logging.basicConfig(format="%(asctime)s: %(message)s", level=logging.INFO, datefmt="%H:%M:%S")
    logging.info("Starting Slippyrouter...")

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(('0.0.0.0', TCP_PORT))
    server.listen(64)

    logging.info(f"Server is listening on 0.0.0.0:{TCP_PORT}")

    serial_reader_thread = threading.Thread(target=serial_reader, daemon=True)
    serial_reader_thread.start()

    server_handler = threading.Thread(target=handle_server, daemon=True, args=(server,))
    server_handler.start()
    
    while True:
        pass