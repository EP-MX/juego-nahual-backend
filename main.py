from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from random import shuffle
from pydantic import BaseModel
from typing import List, Optional
from collections import Counter
from pymongo import ReturnDocument
import random
import string
import secrets


# 1. Configuración de Base de Datos
MONGO_URL = "mongodb+srv://juego_admin:QaSVs2o7Q8uHwLA8@juego.yijg6sl.mongodb.net/?appName=Juego" 
cliente = AsyncIOMotorClient(MONGO_URL)
db = cliente.game_db 


app = FastAPI(title="Servidor de Juego - Lobo", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 3. Modelos de Datos (Cómo FastAPI valida la información)
class CrearSalaRequest(BaseModel):
    nombre_narrador: str

class UnirseSalaRequest(BaseModel):
    nombre_jugador: str
    codigo_sala: str

class IniciarJuegoRequest(BaseModel):
    codigo_sala: str
    nombre_narrador: str
    token: str
    roles_seleccionados: Optional[List[str]] = None

class AccionCupidoRequest(BaseModel):
    codigo_sala: str
    nombre_cupido: str
    enamorado_1: str
    enamorado_2: str
    token: str

class AccionVidenteRequest(BaseModel):
    codigo_sala: str
    nombre_vidente: str
    nombre_objetivo: str
    token: str
class AccionLoboRequest(BaseModel):
    codigo_sala: str
    nombre_lobo: str
    nombre_objetivo: str
    token: str

class AccionBrujaRequest(BaseModel):
    codigo_sala: str
    nombre_bruja: str
    usar_pocion_vida: bool
    objetivo_pocion_muerte: Optional[str] = None
    token: str
class AccionVotoDiaRequest(BaseModel):
    codigo_sala: str
    nombre_votante: str
    nombre_acusado: str
    token: str

class AccionCazadorRequest(BaseModel):
    codigo_sala: str
    nombre_cazador: str
    nombre_objetivo: str
    token: str

class NarradorAvanzarRequest(BaseModel):
    codigo_sala: str
    nombre_narrador: str
    token: str
ROLES_ESPECIALES_VALIDOS = ["Vidente", "Bruja", "Cupido", "Cazador", "Niña"]

#revisar turnos 
def calcular_siguiente_turno(jugadores: list, turno_actual: str) -> str:
    hay_vidente = any(j["rol"] == "Vidente" and j.get("vivo", True) for j in jugadores)
    hay_bruja = any(j["rol"] == "Bruja" and j.get("vivo", True) for j in jugadores)

    flujo_noche = []
    if hay_vidente:
        flujo_noche.append("turno_vidente")
    flujo_noche.append("turno_lobos")
    if hay_bruja:
        flujo_noche.append("turno_bruja")
    flujo_noche.append("esperando_narrador_dia")  
    flujo_noche.append("dia")
    flujo_noche.append("esperando_narrador_noche")

    if turno_actual not in flujo_noche:
        return flujo_noche[0]

    idx_actual = flujo_noche.index(turno_actual)
    
    if idx_actual + 1 < len(flujo_noche):
        return flujo_noche[idx_actual + 1]
    
    return flujo_noche[0]

def verificar_victoria(jugadores: list) -> Optional[str]:
    """Devuelve 'victoria_aldeanos', 'victoria_lobos', o None si el juego debe continuar."""
    lobos_vivos = sum(1 for j in jugadores if j["rol"] == "Hombre Lobo" and j.get("vivo", True))
    aldeanos_vivos = sum(1 for j in jugadores if j["rol"] not in ["Hombre Lobo", "narrador"] and j.get("vivo", True))
    if lobos_vivos == 0:
        return "victoria_aldeanos"
    if lobos_vivos >= aldeanos_vivos:
        return "victoria_lobos"
    return None

# 4. Rutas (Endpoints)

def verificar_jugador(jugadores: list, nombre: str, token: str) -> dict:
    """Busca al jugador por nombre y valida que el token coincida con el que se le asignó al unirse/crear sala."""
    jugador = next((j for j in jugadores if j["nombre"] == nombre), None)
    if not jugador:
        raise HTTPException(status_code=404, detail="Jugador no encontrado en la sala.")
    if jugador.get("token") != token:
        raise HTTPException(status_code=403, detail="Token inválido. Esta sesión no coincide con este jugador.")
    return jugador

@app.get("/sala/{codigo_sala}/votos-lobos")
async def ver_votos_lobos(codigo_sala: str):
    sala = await db.partidas.find_one({"codigo_sala": codigo_sala})
    if not sala:
        raise HTTPException(status_code=404, detail="Sala no encontrada.")
    return {"votos": sala.get("votos_lobos", [])}

@app.get("/")
async def estado_servidor():
    return {"estado": "En línea", "mensaje": "El bosque está despertando..."}

@app.post("/crear-sala")
async def crear_sala(datos: CrearSalaRequest):
    await db.partidas.delete_many({})
    codigo = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
    token_narrador = secrets.token_hex(12)

    nueva_partida = {
        "codigo_sala": codigo,
        "estado": "esperando_jugadores",
        "jugadores": [
            {"nombre": datos.nombre_narrador, "rol": "narrador", "vivo": True, "token": token_narrador}
        ],
        "ciclo": 1
    }
    
    await db.partidas.insert_one(nueva_partida)
    
    return {"mensaje": "Sala creada con éxito", "codigo": codigo, "token": token_narrador}

class UnirseSalaRequest(BaseModel):
    nombre_jugador: str
    codigo_sala: str
    token: Optional[str] = None  # solo se manda al intentar reconectar

@app.post("/unirse-sala")
async def unirse_sala(datos: UnirseSalaRequest):
    sala = await db.partidas.find_one({"codigo_sala": datos.codigo_sala})

    if not sala:
        raise HTTPException(status_code=404, detail="Sala no encontrada. Verifica el código.")

    jugador_existente = next((j for j in sala["jugadores"] if j["nombre"].lower() == datos.nombre_jugador.lower()), None)

    if jugador_existente:
        if sala["estado"] == "esperando_jugadores":
            raise HTTPException(status_code=400, detail="Ese nombre ya está en uso.")
        # La partida ya inició: solo se permite "reconectar" con el token correcto
        if not datos.token or datos.token != jugador_existente.get("token"):
            raise HTTPException(status_code=403, detail="Ese nombre ya pertenece a otro jugador en esta partida.")
        return {"mensaje": f"Reconectando a {datos.nombre_jugador}...", "token": jugador_existente["token"]}

    if sala["estado"] != "esperando_jugadores":
        raise HTTPException(status_code=400, detail="La partida ya comenzó o está cerrada.")

    nuevo_token = secrets.token_hex(12)
    nuevo_jugador = {
        "nombre": datos.nombre_jugador, 
        "rol": "por_asignar", 
        "vivo": True,
        "token": nuevo_token
    }
    
    await db.partidas.update_one(
        {"codigo_sala": datos.codigo_sala},
        {"$push": {"jugadores": nuevo_jugador}}
    )
    
    return {"mensaje": f"¡{datos.nombre_jugador} se ha unido a la sala {datos.codigo_sala}!", "token": nuevo_token}

@app.get("/sala/{codigo_sala}")
async def obtener_sala(codigo_sala: str):
    sala = await db.partidas.find_one({"codigo_sala": codigo_sala})
    
    if not sala:
        raise HTTPException(status_code=404, detail="Sala no encontrada.")
        
    sala["_id"] = str(sala["_id"])
    
    for j in sala.get("jugadores", []):
        j.pop("token", None)
    
    return sala

@app.post("/iniciar-juego")
async def iniciar_juego(datos: IniciarJuegoRequest):
    sala = await db.partidas.find_one({"codigo_sala": datos.codigo_sala})
    
    if not sala:
        raise HTTPException(status_code=404, detail="Sala no encontrada.")
    if sala["estado"] != "esperando_jugadores":
        raise HTTPException(status_code=400, detail="La partida ya comenzó.")

    narrador = verificar_jugador(sala["jugadores"], datos.nombre_narrador, datos.token)
    if narrador["rol"] != "narrador":
        raise HTTPException(status_code=403, detail="Solo el Narrador puede iniciar la partida.")

    jugadores_activos = [j for j in sala["jugadores"] if j["rol"] != "narrador"]
    num_jugadores = len(jugadores_activos)

    if num_jugadores < 5:
        raise HTTPException(status_code=400, detail="Se necesitan al menos 5 jugadores (sin contar al Narrador) para jugar.")

    if num_jugadores >= 12:
        num_lobos = 3
    elif num_jugadores >= 8:
        num_lobos = 2
    else:
        num_lobos = 1

    # Roles especiales que el Narrador decidió incluir (si no manda nada, se incluyen todos por default)
    if datos.roles_seleccionados is not None:
        roles_especiales = [r for r in datos.roles_seleccionados if r in ROLES_ESPECIALES_VALIDOS]
    else:
        roles_especiales = list(ROLES_ESPECIALES_VALIDOS)

    # Los Lobos van primero y siempre entran, sin importar cuántos jugadores haya
    roles_baraja = ["Hombre Lobo"] * num_lobos

    shuffle(roles_especiales)  # si no alcanzan los espacios, que sea al azar cuáles quedan fuera
    espacios_para_especiales = max(0, num_jugadores - num_lobos)
    roles_baraja += roles_especiales[:espacios_para_especiales]

    while len(roles_baraja) < num_jugadores:
        roles_baraja.append("Aldeano")

    shuffle(roles_baraja)

    for i, jugador in enumerate(jugadores_activos):
        jugador["rol"] = roles_baraja[i]
        
        if jugador["rol"] == "Bruja":
            jugador["pocion_vida"] = True
            jugador["pocion_muerte"] = True
            
        jugador["enamorado"] = False
        jugador["alguacil"] = False

    lista_final_jugadores = [narrador] + jugadores_activos

    # Si el Narrador excluyó a Cupido, no hay quién actúe en "turno_cupido" -> saltamos ese turno
    hay_cupido = "Cupido" in roles_baraja
    estado_inicial = "turno_cupido" if hay_cupido else calcular_siguiente_turno(lista_final_jugadores, "turno_cupido")

    await db.partidas.update_one(
        {"codigo_sala": datos.codigo_sala},
        {
            "$set": {
                "estado": estado_inicial,
                "jugadores": lista_final_jugadores,
                "ciclo": 1 
            }
        }
    )

    mensaje = "Partida iniciada. Todos cierran los ojos. Es el turno de Cupido." if hay_cupido else "Partida iniciada. Todos cierran los ojos."
    return {"mensaje": mensaje}

@app.post("/narrador/avanzar")
async def narrador_avanzar(datos: NarradorAvanzarRequest):
    sala = await db.partidas.find_one({"codigo_sala": datos.codigo_sala})
    if not sala:
        raise HTTPException(status_code=404, detail="Sala no encontrada.")

    narrador = verificar_jugador(sala["jugadores"], datos.nombre_narrador, datos.token)
    if narrador["rol"] != "narrador":
        raise HTTPException(status_code=403, detail="No eres el Narrador.")

    jugadores = sala["jugadores"]
    estado_actual = sala["estado"]
    
    # 1. Obtenemos el ciclo para saber en qué noche estamos
    ciclo_actual = sala.get("ciclo", 1)

    # Si hay una victoria esperando a ser anunciada, se revela ahora en vez de seguir el flujo normal
    victoria_pendiente = sala.get("victoria_pendiente")
    if victoria_pendiente:
        await db.partidas.update_one(
            {"codigo_sala": datos.codigo_sala},
            {"$set": {"estado": victoria_pendiente}, "$unset": {"victoria_pendiente": ""}}
        )
        return {"mensaje": "El juego ha terminado.", "estado_siguiente": victoria_pendiente}

    if estado_actual == "esperando_narrador_dia":
        # 2. Verificamos si el Cazador murió en esta misma noche
        cazador_murio_noche = any(
            j["rol"] == "Cazador" and 
            j["vivo"] == False and 
            j.get("ciclo_muerte") == ciclo_actual 
            for j in jugadores
        )
        
        if cazador_murio_noche:
            siguiente = "turno_cazador"
        else:
            siguiente = "dia"

    elif estado_actual == "esperando_narrador_noche":
        hay_vidente = any(j["rol"] == "Vidente" and j.get("vivo", True) for j in jugadores)
        if hay_vidente:
            siguiente = "turno_vidente"
        else:
            siguiente = "turno_lobos"
    else:
        raise HTTPException(status_code=400, detail="No puedes avanzar en este momento.")

    if estado_actual == "esperando_narrador_noche":
        await db.partidas.update_one(
            {"codigo_sala": datos.codigo_sala},
            {
                "$set": {"estado": siguiente},
                "$inc": {"ciclo": 1},
                "$unset": {"ultimo_linchado": ""}
            }
        )
    else:
        await db.partidas.update_one(
            {"codigo_sala": datos.codigo_sala},
            {"$set": {"estado": siguiente}}
        )
    return {"mensaje": f"Narrador avanzó a {siguiente}", "estado_siguiente": siguiente}

@app.post("/accion/cupido")
async def accion_cupido(datos: AccionCupidoRequest):
    sala = await db.partidas.find_one({"codigo_sala": datos.codigo_sala})
    
    if not sala:
        raise HTTPException(status_code=404, detail="Sala no encontrada.")
    if sala["estado"] != "turno_cupido":
        raise HTTPException(status_code=400, detail="Calma, no es el turno de Cupido.")

    jugadores = sala["jugadores"]
    cupido = verificar_jugador(jugadores, datos.nombre_cupido, datos.token)
    if cupido["rol"] != "Cupido":
        raise HTTPException(status_code=403, detail="No eres Cupido.")

    if datos.enamorado_1 == datos.enamorado_2:
        raise HTTPException(status_code=400, detail="No puedes enamorar a la misma persona consigo misma.")

    for j in jugadores:
        if j["nombre"] == datos.enamorado_1 or j["nombre"] == datos.enamorado_2:
            j["enamorado"] = True
    
    siguiente_turno = calcular_siguiente_turno(jugadores, "turno_cupido")  

    await db.partidas.update_one(
        {"codigo_sala": datos.codigo_sala},
        {"$set": {"jugadores": jugadores, "estado": siguiente_turno}}
    )

    return {"mensaje": "Tus flechas han sido lanzadas con éxito.", "estado_siguiente": siguiente_turno}


@app.post("/accion/vidente")
async def accion_vidente(datos: AccionVidenteRequest):
    sala = await db.partidas.find_one({"codigo_sala": datos.codigo_sala})
    
    if not sala:
        raise HTTPException(status_code=404, detail="Sala no encontrada.")
    if sala["estado"] != "turno_vidente":
        raise HTTPException(status_code=400, detail="Aún no es el turno de la Vidente.")

    jugadores = sala["jugadores"]
    vidente = verificar_jugador(jugadores, datos.nombre_vidente, datos.token)
    if vidente["rol"] != "Vidente":
        raise HTTPException(status_code=403, detail="No eres la Vidente.")


    # Buscamos al objetivo
    objetivo = next((j for j in jugadores if j["nombre"] == datos.nombre_objetivo), None)
    
    if not objetivo:
        raise HTTPException(status_code=404, detail="El jugador objetivo no existe.")

    error_muerto = False
    rol_descubierto = objetivo["rol"]

    if not objetivo.get("vivo", True):
        # Si está muerto, marcamos el error pero NO lanzamos HTTPException
        error_muerto = True
        rol_descubierto = "DESCONOCIDO (Por investigar a un muerto)"

    # SIEMPRE avanzamos el turno, sin importar si eligió a un muerto o no
    siguiente_turno = calcular_siguiente_turno(jugadores, "turno_vidente")
    
    await db.partidas.update_one(
        {"codigo_sala": datos.codigo_sala},
        {"$set": {"estado": siguiente_turno}}
    )

    if error_muerto:
        return {
            "mensaje": "¡Tu bola de cristal se oscurece! No puedes investigar a los muertos y has perdido tu turno.",
            "rol_descubierto": rol_descubierto,
            "estado_siguiente": siguiente_turno
        }

    return {
        "mensaje": f"Has mirado en tu bola de cristal... {datos.nombre_objetivo} es: {rol_descubierto}",
        "rol_descubierto": rol_descubierto,
        "estado_siguiente": siguiente_turno
    }

@app.post("/accion/lobos")
async def accion_lobos(datos: AccionLoboRequest):
    sala = await db.partidas.find_one({"codigo_sala": datos.codigo_sala})
    
    if not sala:
        raise HTTPException(status_code=404, detail="Sala no encontrada.")
    if sala["estado"] != "turno_lobos":
        raise HTTPException(status_code=400, detail="Aún no es el turno de los Hombres Lobo.")

    lobo = verificar_jugador(sala["jugadores"], datos.nombre_lobo, datos.token)
    if lobo["rol"] != "Hombre Lobo" or not lobo.get("vivo", True):
        raise HTTPException(status_code=403, detail="No eres un Lobo o estás muerto.")

    sala_actualizada = await db.partidas.find_one_and_update(
        {
            "codigo_sala": datos.codigo_sala,
            "estado": "turno_lobos",
            "votos_lobos.lobo": {"$ne": datos.nombre_lobo}
        },
        {"$push": {"votos_lobos": {"lobo": datos.nombre_lobo, "voto": datos.nombre_objetivo}}},
        return_document=ReturnDocument.AFTER
    )

    if sala_actualizada is None:
        ya_voto = any(v["lobo"] == datos.nombre_lobo for v in sala.get("votos_lobos", []))
        if ya_voto:
            raise HTTPException(status_code=400, detail="Ya emitiste tu voto esta noche.")
        raise HTTPException(status_code=400, detail="El turno de los lobos ya no está activo.")

    jugadores = sala_actualizada["jugadores"]
    votos_actuales = sala_actualizada.get("votos_lobos", [])
    lobos_vivos = [j for j in jugadores if j["rol"] == "Hombre Lobo" and j.get("vivo", True)]
    total_lobos = len(lobos_vivos)

    if len(votos_actuales) < total_lobos:
        return {"mensaje": f"Voto registrado. Esperando a los demás lobos... ({len(votos_actuales)}/{total_lobos})"}

    primer_voto = votos_actuales[0]["voto"]
    hay_unanimidad = all(v["voto"] == primer_voto for v in votos_actuales)
    victima = primer_voto if hay_unanimidad else None

    await db.partidas.update_one(
        {"codigo_sala": datos.codigo_sala},
        {
            "$set": {
                "estado": "confirmando_lobos",
                "victima_lobos": victima,
                "votos_lobos": votos_actuales,
                "ultimo_consenso": victima
            }
        }
    )
    
    import asyncio
    await asyncio.sleep(5)

    hay_bruja = any(j["rol"] == "Bruja" and j.get("vivo", True) for j in jugadores)
    muertos_esta_noche = []  

    ciclo_actual = sala.get("ciclo", 1)
    if not hay_bruja and victima:
        for j in jugadores:
            if j["nombre"] == victima and j.get("vivo", True):
                j["vivo"] = False
                j["ciclo_muerte"] = ciclo_actual
                muertos_esta_noche.append(victima)
                if j.get("enamorado"):
                    for j2 in jugadores:
                        if j2.get("enamorado") and j2["nombre"] != victima and j2.get("vivo", True):
                            j2["vivo"] = False
                            j2["ciclo_muerte"] = ciclo_actual
                            muertos_esta_noche.append(j2["nombre"])
                break

    estado_siguiente = calcular_siguiente_turno(jugadores, "turno_lobos")
    victoria = verificar_victoria(jugadores)

    update_op = {
        "$set": {
            "estado": estado_siguiente,
            "jugadores": jugadores,
            "votos_lobos": [],
            "reporte_muertes": muertos_esta_noche
        }
    }
    if not hay_bruja:
        update_op["$unset"] = {"victima_lobos": ""}
    if victoria:
        update_op["$set"]["victoria_pendiente"] = victoria
    else:
        update_op.setdefault("$unset", {})["victoria_pendiente"] = ""

    await db.partidas.update_one({"codigo_sala": datos.codigo_sala}, update_op)
    mensaje_final = "Todos los lobos han votado. "
    mensaje_final += "Hay consenso." if hay_unanimidad else "No hubo unanimidad, la víctima se ha salvado."

    return {
        "mensaje": mensaje_final,
        "hay_victima": hay_unanimidad,
        "estado_siguiente": estado_siguiente 
    }

@app.post("/accion/bruja")
async def accion_bruja(datos: AccionBrujaRequest):
    sala = await db.partidas.find_one({"codigo_sala": datos.codigo_sala})
    if not sala:
        raise HTTPException(status_code=404, detail="Sala no encontrada.")
    if sala["estado"] != "turno_bruja":
        raise HTTPException(status_code=400, detail="Aún no es el turno de la Bruja.")

    jugadores = sala["jugadores"]
    bruja = verificar_jugador(jugadores, datos.nombre_bruja, datos.token)
    if bruja["rol"] != "Bruja" or not bruja.get("vivo", True):
        raise HTTPException(status_code=403, detail="No eres la Bruja o estás muerta.")


    victima_lobos = sala.get("victima_lobos")
    muertos_esta_noche = set()

    # 3. Poción de Vida
    if datos.usar_pocion_vida:
        if not bruja.get("pocion_vida"):
            raise HTTPException(status_code=400, detail="Ya gastaste tu poción de vida.")
        bruja["pocion_vida"] = False #se gasto
    elif victima_lobos:
        muertos_esta_noche.add(victima_lobos)

    # 4. Poción de Muerte
    if datos.objetivo_pocion_muerte:
        if not bruja.get("pocion_muerte"):
            raise HTTPException(status_code=400, detail="Ya gastaste tu poción de muerte.")
        bruja["pocion_muerte"] = False #se gasto
        muertos_esta_noche.add(datos.objetivo_pocion_muerte)

    # Si alguien de los que va a morir estaba enamorado el otro también muere.
    muertos_finales = list(muertos_esta_noche) 
    for nombre_muerto in muertos_finales:
        jugador_muerto = next((j for j in jugadores if j["nombre"] == nombre_muerto), None)
        if jugador_muerto and jugador_muerto.get("enamorado"):
            for j in jugadores:
                if j.get("enamorado") and j["nombre"] != nombre_muerto:
                    muertos_esta_noche.add(j["nombre"])

# 6. Aplicar las muertes en la base de datos
    ciclo_actual = sala.get("ciclo", 1)
    for j in jugadores:
        if j["nombre"] in muertos_esta_noche:
            j["vivo"] = False
            j["ciclo_muerte"] = ciclo_actual

    # LÓGICA DE VICTORIA 
    #estado_siguiente = calcular_siguiente_turno(jugadores, "turno_bruja") # <-- CAMBIADA
    estado_siguiente = "esperando_narrador_dia"
    victoria = verificar_victoria(jugadores)

    update_op = {
        "$set": {
            "estado": estado_siguiente,
            "jugadores": jugadores,
            "reporte_muertes": list(muertos_esta_noche)
        },
        "$unset": {
            "victima_lobos": ""
        }
    }
    if victoria:
        update_op["$set"]["victoria_pendiente"] = victoria
    else:
        update_op["$unset"]["victoria_pendiente"] = ""

    await db.partidas.update_one({"codigo_sala": datos.codigo_sala}, update_op)

    return {
        "mensaje": "Has mezclado tus pociones. La noche termina...",
        "estado_siguiente": estado_siguiente,
        "bajas_totales": list(muertos_esta_noche)
    }

@app.post("/accion/votar-dia")
async def votar_dia(datos: AccionVotoDiaRequest):
    sala = await db.partidas.find_one({"codigo_sala": datos.codigo_sala})
    if not sala:
        raise HTTPException(status_code=404, detail="Sala no encontrada.")
    if sala["estado"] != "dia":
        raise HTTPException(status_code=400, detail="No es de día. No se puede votar.")

    votante = verificar_jugador(sala["jugadores"], datos.nombre_votante, datos.token)
    if not votante.get("vivo", True) or votante["rol"] == "narrador":
        raise HTTPException(status_code=403, detail="No puedes votar. Estás muerto o no eres jugador.")

    peso_voto = 2 if votante.get("alguacil") else 1

    sala_actualizada = await db.partidas.find_one_and_update(
        {
            "codigo_sala": datos.codigo_sala,
            "estado": "dia",
            "votos_dia.votante": {"$ne": datos.nombre_votante}
        },
        {"$push": {"votos_dia": {
            "votante": datos.nombre_votante,
            "acusado": datos.nombre_acusado,
            "peso": peso_voto
        }}},
        return_document=ReturnDocument.AFTER
    )

    if sala_actualizada is None:
        ya_voto = any(v["votante"] == datos.nombre_votante for v in sala.get("votos_dia", []))
        if ya_voto:
            raise HTTPException(status_code=400, detail="Ya emitiste tu voto.")
        raise HTTPException(status_code=400, detail="La votación ya no está activa.")

    jugadores = sala_actualizada["jugadores"]
    votos_actuales = sala_actualizada.get("votos_dia", [])
    jugadores_vivos = [j for j in jugadores if j.get("vivo", True) and j["rol"] != "narrador"]

    if len(votos_actuales) < len(jugadores_vivos):
        return {"mensaje": f"Voto registrado. Esperando a los demás... ({len(votos_actuales)}/{len(jugadores_vivos)})"}

    # 5. contar los votos  -> de aquí en adelante, todo sigue exactamente igual que tu versión original
    conteo = Counter()
    for voto in votos_actuales:
        conteo[voto["acusado"]] += voto["peso"]

    # Obtenemos al más votado (linchado)
    mas_votado = conteo.most_common(1)[0]
    nombre_linchado = mas_votado[0]
    
    # Manejo de empates
    hubo_empate = False
    if len(conteo) > 1:
        segundo_mas_votado = conteo.most_common(2)[1]
        if mas_votado[1] == segundo_mas_votado[1]:
            hubo_empate = True

    muertos_por_linchamiento = set()
    estado_siguiente = calcular_siguiente_turno(jugadores, "dia") # <-- CAMBIADA

    if not hubo_empate and nombre_linchado != "abstencion":
        muertos_por_linchamiento.add(nombre_linchado)
        
        #El suicidio de Cupido 
        jugador_linchado = next(j for j in jugadores if j["nombre"] == nombre_linchado)
        if jugador_linchado.get("enamorado"):
            for j in jugadores:
                if j.get("enamorado") and j["nombre"] != nombre_linchado:
                    muertos_por_linchamiento.add(j["nombre"])

        # El Cazador 
        for nombre in muertos_por_linchamiento:
            jug_temp = next(j for j in jugadores if j["nombre"] == nombre)
            if jug_temp["rol"] == "Cazador":
                estado_siguiente = "turno_cazador"

        # Aplicar las muertes en la BD
        ciclo_actual = sala.get("ciclo", 1)
        for j in jugadores:
            if j["nombre"] in muertos_por_linchamiento:
                j["vivo"] = False
                j["ciclo_muerte"] = sala.get("ciclo", 1)

    # VICTORIA
   
    victoria = verificar_victoria(jugadores)

    update_op = {
        "$set": {
            "estado": estado_siguiente,
            "jugadores": jugadores,
            "ultimo_linchado": list(muertos_por_linchamiento) if not hubo_empate else []
        },
        "$unset": {
            "votos_dia": ""
        }
    }
    if victoria:
        update_op["$set"]["victoria_pendiente"] = victoria
    else:
        update_op["$unset"]["victoria_pendiente"] = ""

    await db.partidas.update_one({"codigo_sala": datos.codigo_sala}, update_op)

    mensaje_final = "El pueblo ha hablado. "
    if hubo_empate:
        mensaje_final += "Nadie es linchado hoy."
    else:
        mensaje_final += f"{nombre_linchado} ha sido linchado. "

    return {
        "mensaje": mensaje_final,
        "linchados": list(muertos_por_linchamiento),
        "estado_siguiente": estado_siguiente
    }


@app.post("/accion/cazador")
async def accion_cazador(datos: AccionCazadorRequest):
    sala = await db.partidas.find_one({"codigo_sala": datos.codigo_sala})
    if not sala:
        raise HTTPException(status_code=404, detail="Sala no encontrada.")
    if sala["estado"] != "turno_cazador":
        raise HTTPException(status_code=400, detail="No es el turno del Cazador.")

    jugadores = sala["jugadores"]
    cazador = verificar_jugador(jugadores, datos.nombre_cazador, datos.token)
    if cazador["rol"] != "Cazador":
        raise HTTPException(status_code=403, detail="No eres el Cazador.")

    # Procesar el disparo si el objetivo existe y está vivo
    objetivo = next((j for j in jugadores if j["nombre"] == datos.nombre_objetivo), None)

    if objetivo and objetivo.get("vivo", True):
        ciclo_actual = sala.get("ciclo", 1)
        for j in jugadores:
            if j["nombre"] == datos.nombre_objetivo:
                j["vivo"] = False
                j["ciclo_muerte"] = ciclo_actual
                # EFECTO DOMINÓ: Si el objetivo estaba enamorado, muere su pareja
                if j.get("enamorado"):
                    for pareja in jugadores:
                        if pareja.get("enamorado") and pareja["nombre"] != datos.nombre_objetivo and pareja.get("vivo", True):
                            pareja["vivo"] = False
                            pareja["ciclo_muerte"] = ciclo_actual
    else:
        raise HTTPException(status_code=400, detail="Objetivo no válido o ya muerto.")

    # Lógica de Victoria / Siguiente Turno
    victoria = verificar_victoria(jugadores)

    if sala.get("ultimo_linchado"):
        estado_siguiente = "esperando_narrador_noche"
    elif victoria:
        estado_siguiente = "esperando_narrador_dia"  # gate: el Narrador revela la victoria al avanzar
    else:
        estado_siguiente = "dia"

    update_op = {"$set": {"estado": estado_siguiente, "jugadores": jugadores}}
    if victoria:
        update_op["$set"]["victoria_pendiente"] = victoria
    else:
        update_op["$unset"] = {"victoria_pendiente": ""}

    await db.partidas.update_one({"codigo_sala": datos.codigo_sala}, update_op)

    return {
        "mensaje": f"El Cazador dispara su última bala a {datos.nombre_objetivo}.",
        "estado_siguiente": estado_siguiente
    }