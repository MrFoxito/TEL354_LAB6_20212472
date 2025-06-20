import yaml
import os
import sys
import requests
import json


# Clases principales


class Alumno:
    def __init__(self, nombre, codigo, mac):
        self.nombre = nombre
        self.codigo = codigo
        self.mac = mac


class Servicio:
    def __init__(self, nombre, protocolo, puerto):
        self.nombre = nombre
        self.protocolo = protocolo
        self.puerto = puerto


class Servidor:
    def __init__(self, nombre, ip, servicios=None):
        self.nombre = nombre
        self.ip = ip
        self.servicios = servicios if servicios else []


class Curso:
    def __init__(self, codigo, estado, nombre, alumnos=None, servidores=None):
        self.codigo = codigo
        self.estado = estado
        self.nombre = nombre
        self.alumnos = alumnos if alumnos else []
        self.servidores = servidores if servidores else []


class Conexion:
    def __init__(self, handler, alumno, servidor, servicio):
        self.handler = handler
        self.alumno = alumno
        self.servidor = servidor
        self.servicio = servicio


# Funciones de import/export YAML


def importar_datos(filename):
    with open(filename, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)
    return data


def exportar_datos(filename, data):
    with open(filename, 'w', encoding='utf-8') as f:
        yaml.dump(data, f, allow_unicode=True)






def get_attachment_point(controller_ip, mac):
    url = f'http://{controller_ip}:8080/wm/device/'
    response = requests.get(url)
    if response.status_code == 200:
        devices = response.json()
        for device in devices:
            if mac.lower() in [m.lower() for m in device.get('mac', [])]:
                ap = device.get('attachmentPoint', [])
                if ap:
                    return ap[0]['switchDPID'], ap[0]['port']
    return None, None


def get_route(controller_ip, src_dpid, src_port, dst_dpid, dst_port):
    url = f'http://{controller_ip}:8080/wm/topology/route/{src_dpid}/{src_port}/{dst_dpid}/{dst_port}/json'
    response = requests.get(url)
    if response.status_code == 200:
        path = response.json()
        return [(hop['switch'], hop['port']) for hop in path]
    return []


def push_flow_to_floodlight(controller_ip, flow):
    url = f'http://{controller_ip}:8080/wm/staticentrypusher/json'
    headers = {'Content-type': 'application/json'}
    response = requests.post(url, data=json.dumps(flow), headers=headers)
    if response.status_code == 200:
        print(f"Flow '{flow['name']}' insertado correctamente en Floodlight.")
    else:
        print(f"Error al insertar flow '{flow['name']}': {response.status_code} {response.text}")


def build_route(ruta, datos_conexion, controller_ip='localhost'):
    # datos_conexion: dict con keys: mac_src, mac_dst, ip_src, ip_dst, puerto_l4, protocolo ('TCP'/'UDP')
    proto_num = '0x06' if datos_conexion['protocolo'].upper() == 'TCP' else '0x11'
    # Flujos en sentido alumno -> servidor
    for i in range(len(ruta)-1):
        sw, in_port = ruta[i]
        _, out_port = ruta[i+1]
        flow = {
            "switch": sw,
            "name": f"flow_{datos_conexion['mac_src']}_{datos_conexion['mac_dst']}_{i}_fwd",
            "cookie": "0",
            "priority": "32768",
            "in_port": str(in_port),
            "eth_type": "0x0800",
            "ip_proto": proto_num,
            "ipv4_src": datos_conexion['ip_src'],
            "ipv4_dst": datos_conexion['ip_dst'],
            f"{datos_conexion['protocolo'].lower()}_dst": str(datos_conexion['puerto_l4']),
            "active": "true",
            "actions": f"output={out_port}"
        }
        push_flow_to_floodlight(controller_ip, flow)
    # Flujos en sentido servidor -> alumno
    for i in range(len(ruta)-1):
        sw, in_port = ruta[-(i+1)]
        _, out_port = ruta[-(i+2)] if i+2 <= len(ruta) else (None, None)
        if out_port is None:
            continue
        flow = {
            "switch": sw,
            "name": f"flow_{datos_conexion['mac_dst']}_{datos_conexion['mac_src']}_{i}_rev",
            "cookie": "0",
            "priority": "32768",
            "in_port": str(in_port),
            "eth_type": "0x0800",
            "ip_proto": proto_num,
            "ipv4_src": datos_conexion['ip_dst'],
            "ipv4_dst": datos_conexion['ip_src'],
            f"{datos_conexion['protocolo'].lower()}_src": str(datos_conexion['puerto_l4']),
            "active": "true",
            "actions": f"output={out_port}"
        }
        push_flow_to_floodlight(controller_ip, flow)
       
    # Flujos para ARP en ambos sentidos
    for i in range(len(ruta)-1):
        sw, in_port = ruta[i]
        _, out_port = ruta[i+1]
        flow_arp_fwd = {
            "switch": sw,
            "name": f"arp_{datos_conexion['mac_src']}_{datos_conexion['mac_dst']}_{i}_fwd",
            "cookie": "0",
            "priority": "32768",
            "in_port": str(in_port),
            "eth_type": "0x0806",
            "ipv4_src": datos_conexion['ip_src'],
            "ipv4_dst": datos_conexion['ip_dst'],
            "active": "true",
            "actions": f"output={out_port}"
        }
        push_flow_to_floodlight(controller_ip, flow_arp_fwd)
        # ARP reverso
        flow_arp_rev = {
            "switch": sw,
            "name": f"arp_{datos_conexion['mac_dst']}_{datos_conexion['mac_src']}_{i}_rev",
            "cookie": "0",
            "priority": "32768",
            "in_port": str(out_port),
            "eth_type": "0x0806",
            "ipv4_src": datos_conexion['ip_dst'],
            "ipv4_dst": datos_conexion['ip_src'],
            "active": "true",
            "actions": f"output={in_port}"
        }
        push_flow_to_floodlight(controller_ip, flow_arp_rev)
    print("Flows instalados para la ruta en ambos sentidos y para ARP.")




# Menú principal y submenús
def menu():
    while True:
        print("""
###############################################
Network Policy manager de la UPSM
###############################################
Seleccione una opción:
1) Importar
2) Exportar
3) Cursos
4) Alumnos
5) Servidores
6) Políticas
7) Conexiones
8) Salir
>>> """, end='')
        opcion = input().strip()
        if opcion == '1':
            importar_menu()
        elif opcion == '2':
            exportar_menu()
        elif opcion == '3':
            cursos_menu()
        elif opcion == '4':
            alumnos_menu()
        elif opcion == '5':
            servidores_menu()
        elif opcion == '6':
            politicas_menu()
        elif opcion == '7':
            conexiones_menu()
        elif opcion == '8':
            print("Saliendo...")
            break
        else:
            print("Opción inválida. Intente de nuevo.")


# Submenus


def importar_menu():
    print("Nombre de archivo a importar:", end=' ')
    filename = input().strip()
    if not os.path.exists(filename):
        print(f"Archivo {filename} no encontrado.")
        return
    data = importar_datos(filename)
    listar_alumnos.data = data
    print(f"Importado {filename}")


def exportar_menu():
    print("Nombre de archivo a exportar:", end=' ')
    filename = input().strip()
    if not hasattr(listar_alumnos, 'data'):
        print("No hay datos cargados para exportar.")
        return
    data = listar_alumnos.data
    exportar_datos(filename, data)
    print(f"Exportado a {filename}")


def cursos_menu():
    print("""
1) Listar
2) Mostrar detalle
3) Actualizar (agregar/eliminar alumno)
4) Listar cursos con acceso a un servicio en un servidor
5) Volver
>>> """, end='')
    opcion = input().strip()
    if opcion == '1':
        listar_cursos()
    elif opcion == '2':
        mostrar_detalle_curso()
    elif opcion == '3':
        actualizar_curso()
    elif opcion == '4':
        listar_cursos_servicio_servidor()
    elif opcion == '5':
        return
    else:
        print("Opción inválida. Intente de nuevo.")
        cursos_menu()  # Volver a mostrar el menú de cursos


def listar_cursos():
    if not hasattr(listar_alumnos, 'data'):
        print("Primero importe los datos con la opción 1 del menú principal.")
        return
    data = listar_alumnos.data
    print("\nCursos registrados:")
    for curso in data.get('cursos', []):
        print(f"- {curso['codigo']} | {curso['nombre']} | Estado: {curso['estado']}")
    print()


def mostrar_detalle_curso():
    if not hasattr(listar_alumnos, 'data'):
        print("Primero importe los datos con la opción 1 del menú principal.")
        return
    data = listar_alumnos.data
    codigo = input("Ingrese el código del curso: ").strip()
    for curso in data.get('cursos', []):
        if str(curso['codigo']) == codigo:
            print(f"Código: {curso['codigo']}")
            print(f"Nombre: {curso['nombre']}")
            print(f"Estado: {curso['estado']}")
            print(f"Alumnos: {curso.get('alumnos', [])}")
            print(f"Servidores: {curso.get('servidores', [])}")
            return
    print("Curso no encontrado.")


def actualizar_curso():
    if not hasattr(listar_alumnos, 'data'):
        print("Primero importe los datos con la opción 1 del menú principal.")
        return
    data = listar_alumnos.data
    codigo = input("Código del curso a actualizar: ").strip()
    curso = next((c for c in data.get('cursos', []) if str(c['codigo']) == codigo), None)
    if not curso:
        print("Curso no encontrado.")
        return
    print("1) Agregar alumno\n2) Eliminar alumno")
    op = input("Seleccione opción: ").strip()
    if op == '1':
        cod_alumno = input("Código del alumno a agregar: ").strip()
        if cod_alumno not in curso['alumnos']:
            curso['alumnos'].append(cod_alumno)
            print("Alumno agregado al curso.")
        else:
            print("El alumno ya está en el curso.")
    elif op == '2':
        cod_alumno = input("Código del alumno a eliminar: ").strip()
        if cod_alumno in curso['alumnos']:
            curso['alumnos'].remove(cod_alumno)
            print("Alumno eliminado del curso.")
        else:
            print("El alumno no está en el curso.")


def alumnos_menu():
    print("""
1) Listar
2) Mostrar detalle
3) Agregar
4) Borrar
5) Volver
>>> """, end='')
    opcion = input().strip()
    if opcion == '1':
        listar_alumnos()
    elif opcion == '2':
        mostrar_detalle_alumno()
    elif opcion == '3':
        agregar_alumno()
    elif opcion == '4':
        borrar_alumno()
    # Volver al menú anterior
    elif opcion == '5':
        return
    else:
        print("Opción inválida. Intente de nuevo.")
        alumnos_menu()  # Volver a mostrar el menú de alumnos


def listar_alumnos():
    if not hasattr(listar_alumnos, 'data'):
        print("Primero importe los datos con la opción 1 del menú principal.")
        return
    data = listar_alumnos.data
    print("\nAlumnos registrados:")
    for alumno in data.get('alumnos', []):
        print(f"- {alumno['nombre']} (Código: {alumno['codigo']}, MAC: {alumno['mac']})")
    print()


def mostrar_detalle_alumno():
    if not hasattr(listar_alumnos, 'data'):
        print("Primero importe los datos con la opción 1 del menú principal.")
        return
    data = listar_alumnos.data
    codigo = input("Ingrese el código del alumno: ").strip()
    for alumno in data.get('alumnos', []):
        if str(alumno['codigo']) == codigo:
            print(f"Nombre: {alumno['nombre']}")
            print(f"Código: {alumno['codigo']}")
            print(f"MAC: {alumno['mac']}")
            return
    print("Alumno no encontrado.")


def agregar_alumno():
    if not hasattr(listar_alumnos, 'data'):
        print("Primero importe los datos con la opción 1 del menú principal.")
        return
    data = listar_alumnos.data
    nombre = input("Nombre del alumno: ").strip()
    codigo = input("Código del alumno: ").strip()
    mac = input("MAC del alumno: ").strip()
    if any(str(a['codigo']) == codigo for a in data.get('alumnos', [])):
        print("Ya existe un alumno con ese código.")
        return
    data['alumnos'].append({'nombre': nombre, 'codigo': codigo, 'mac': mac})
    print(f"Alumno {nombre} agregado.")


def borrar_alumno():
    if not hasattr(listar_alumnos, 'data'):
        print("Primero importe los datos con la opción 1 del menú principal.")
        return
    data = listar_alumnos.data
    codigo = input("Código del alumno a borrar: ").strip()
    for i, alumno in enumerate(data.get('alumnos', [])):
        if str(alumno['codigo']) == codigo:
            data['alumnos'].pop(i)
            for curso in data.get('cursos', []):
                if codigo in [str(c) for c in curso.get('alumnos', [])]:
                    curso['alumnos'] = [c for c in curso['alumnos'] if str(c) != codigo]
            print("Alumno borrado correctamente.")
            return
    print("Alumno no encontrado.")


def servidores_menu():
    print("""
1) Listar
2) Mostrar detalle
3) Volver
>>> """, end='')
    opcion = input().strip()
    if opcion == '1':
        listar_servidores()
    elif opcion == '2':
        mostrar_detalle_servidor()
    # Volver
    elif opcion == '3':
        return
    else:
        print("Opción inválida. Intente de nuevo.")
        servidores_menu()  # Volver


def listar_servidores():
    if not hasattr(listar_alumnos, 'data'):
        print("Primero importe los datos con la opción 1 del menú principal.")
        return
    data = listar_alumnos.data
    print("\nServidores registrados:")
    for servidor in data.get('servidores', []):
        print(f"- {servidor['nombre']} (IP: {servidor['ip']})")
    print()


def mostrar_detalle_servidor():
    if not hasattr(listar_alumnos, 'data'):
        print("Primero importe los datos con la opción 1 del menú principal.")
        return
    data = listar_alumnos.data
    nombre = input("Ingrese el nombre del servidor: ").strip()
    for servidor in data.get('servidores', []):
        if servidor['nombre'] == nombre:
            print(f"Nombre: {servidor['nombre']}")
            print(f"IP: {servidor['ip']}")
            print("Servicios:")
            for srv in servidor.get('servicios', []):
                print(f"  - {srv['nombre']} | Protocolo: {srv['protocolo']} | Puerto: {srv['puerto']}")
            return
    print("Servidor no encontrado.")


def politicas_menu():
    print("(No implementado en este laboratorio)")


def conexiones_menu():
    print("""
1) Crear
2) Listar
3) Borrar
4) Volver
>>> """, end='')
    opcion = input().strip()
    if opcion == '1':
        crear_conexion()
    elif opcion == '2':
        listar_conexiones()
    elif opcion == '3':
        borrar_conexion()
    # Volver
    elif opcion == '4':
        return
    else:
        print("Opción inválida. Intente de nuevo.")
        conexiones_menu()  # Volver


# Conexiones manuales
conexiones = []


def crear_conexion():
    if not hasattr(listar_alumnos, 'data'):
        print("Primero importe los datos con la opción 1 del menú principal.")
        return
    data = listar_alumnos.data
    cod_alumno = input("Código del alumno: ").strip()
    nombre_servidor = input("Nombre del servidor: ").strip()
    nombre_servicio = input("Nombre del servicio: ").strip()
    controller_ip = input("IP del controlador Floodlight (default: localhost): ").strip() or 'localhost'
    # Buscar alumno
    alumno = next((a for a in data.get('alumnos', []) if str(a['codigo']) == cod_alumno), None)
    if not alumno:
        print("Alumno no encontrado.")
        return
    # Buscar servidor
    servidor = next((s for s in data.get('servidores', []) if s['nombre'] == nombre_servidor), None)
    if not servidor:
        print("Servidor no encontrado.")
        return
    # Buscar servicio
    servicio = next((srv for srv in servidor.get('servicios', []) if srv['nombre'] == nombre_servicio), None)
    if not servicio:
        print("Servicio no encontrado en el servidor.")
        return    # Validar políticas
    autorizado = False
    for curso in data.get('cursos', []):
        if curso['estado'] == 'DICTANDO' and cod_alumno in [str(c) for c in curso.get('alumnos', [])]:
            for srv in curso.get('servidores', []):
                if srv['nombre'] == nombre_servidor and nombre_servicio in srv.get('servicios_permitidos', []):
                    autorizado = True
    if not autorizado:
        print("El alumno NO está autorizado para acceder a ese servicio en ese servidor.")
        return
    handler = f"{cod_alumno}-{nombre_servidor}-{nombre_servicio}"
    conexiones.append({'handler': handler, 'alumno': cod_alumno, 'servidor': nombre_servidor, 'servicio': nombre_servicio})
    print(f"Conexión creada. Handler: {handler}")
    # Obtener MAC/IP origen y destino
    mac_src = alumno['mac']
    ip_src = input("IP del alumno (host origen): ").strip()
    mac_dst = servidor['servicios'][0].get('mac', '')  # Si tienes la MAC del servidor
    ip_dst = servidor['ip']
    puerto_l4 = servicio['puerto']
    protocolo = servicio['protocolo']
    # Obtener punto de conexión (DPID y puerto) del alumno y servidor
    src_dpid, src_port = get_attachment_point(controller_ip, mac_src)
    dst_dpid, dst_port = get_attachment_point(controller_ip, mac_dst) if mac_dst else (None, None)
    if not src_dpid or not src_port or not dst_dpid or not dst_port:
        print("No se pudo obtener el punto de conexión de origen o destino. Verifica las MACs e IPs.")
        return
    # Obtener ruta
    ruta = get_route(controller_ip, src_dpid, src_port, dst_dpid, dst_port)
    if not ruta:
        print("No se pudo calcular la ruta entre el alumno y el servidor.")
        return
    datos_conexion = {
        'mac_src': mac_src,
        'mac_dst': mac_dst,
        'ip_src': ip_src,
        'ip_dst': ip_dst,
        'puerto_l4': puerto_l4,
        'protocolo': protocolo
    }
    build_route(ruta, datos_conexion, controller_ip)


def listar_conexiones():
    if not conexiones:
        print("No hay conexiones manuales creadas.")
        return
    print("Conexiones manuales:")
    for c in conexiones:
        print(f"Handler: {c['handler']} | Alumno: {c['alumno']} | Servidor: {c['servidor']} | Servicio: {c['servicio']}")
    print()


def borrar_conexion():
    handler = input("Handler de la conexión a borrar: ").strip()
    for i, c in enumerate(conexiones):
        if c['handler'] == handler:
            conexiones.pop(i)
            print("Conexión eliminada.")
            return
    print("Conexión no encontrada.")


def listar_alumnos_curso():
    if not hasattr(listar_alumnos, 'data'):
        print("Primero importe los datos con la opción 1 del menú principal.")
        return
    data = listar_alumnos.data
    codigo = input("Ingrese el código del curso: ").strip()
    curso = next((c for c in data.get('cursos', []) if str(c['codigo']) == codigo), None)
    if not curso:
        print("Curso no encontrado.")
        return
    print(f"Alumnos en el curso {codigo}:")
    for cod in curso.get('alumnos', []):
        alumno = next((a for a in data.get('alumnos', []) if str(a['codigo']) == str(cod)), None)
        if alumno:
            print(f"- {alumno['nombre']} (Código: {alumno['codigo']}, MAC: {alumno['mac']})")
    print()


def listar_cursos_servicio_servidor():
    if not hasattr(listar_alumnos, 'data'):
        print("Primero importe los datos con la opción 1 del menú principal.")
        return
    data = listar_alumnos.data
    servicio = input("Nombre del servicio (ej: ssh): ").strip()
    servidor = input("Nombre del servidor: ").strip()
    print(f"Cursos con acceso a {servicio} en {servidor}:")
    for curso in data.get('cursos', []):
        for srv in curso.get('servidores', []):
            if srv['nombre'] == servidor and servicio in srv.get('servicios_permitidos', []):
                print(f"- {curso['codigo']} | {curso['nombre']}")
    print()


# Main


def main():
    if os.path.exists('datos.yaml'):
        data = importar_datos('datos.yaml')
        listar_alumnos.data = data
    else:
        data = {}
    menu()


if __name__ == "__main__":
    main()



