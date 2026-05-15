from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from random import shuffle
from pydantic import BaseModel
from typing import Optional 
from collections import Counter
import random
import string

# 1. Configuración de Base de Datos
MONGO_URL = "mongodb+srv://juego_admin:QaSVs2o7Q8uHwLA8@juego.yijg6sl.mongodb.net/?appName=Juego" # <--- ¡Pega tu link aquí!
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

class AccionCupidoRequest(BaseModel):
    codigo_sala: str
    nombre_cupido: str
    enamorado_1: str
    enamorado_2: str

class AccionVidenteRequest(BaseModel):
    codigo_sala: str
    nombre_vidente: str
    nombre_objetivo: str

class AccionLoboRequest(BaseModel):
    codigo_sala: str
    nombre_lobo: str
    nombre_objetivo: str

class AccionBrujaRequest(BaseModel):
    codigo_sala: str
    nombre_bruja: str
    usar_pocion_vida: bool
    objetivo_pocion_muerte: Optional[str] = None

class AccionVotoDiaRequest(BaseModel):
    codigo_sala: str
    nombre_votante: str
    nombre_acusado: str 

class AccionCazadorRequest(BaseModel):
    codigo_sala: str
    nombre_cazador: str
    nombre_objetivo: str

class NarradorAvanzarRequest(BaseModel):
    codigo_sala: str
    nombre_narrador: str

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
# 4. Rutas (Endpoints)

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

    nueva_partida = {
        "codigo_sala": codigo,
        "estado": "esperando_jugadores",
        "jugadores": [
            {"nombre": datos.nombre_narrador, "rol": "narrador", "vivo": True}
        ],
        "ciclo": 1 # Iniciamos el contador de días aquí por seguridad
    }
    
   
    await db.partidas.insert_one(nueva_partida)
    
    return {"mensaje": "Sala creada con éxito", "codigo": codigo}

@app.post("/unirse-sala")
async def unirse_sala(datos: UnirseSalaRequest):
    sala = await db.partidas.find_one({"codigo_sala": datos.codigo_sala})

    if not sala:
        raise HTTPException(status_code=404, detail="Sala no encontrada. Verifica el código.")

    nombre_existe = any(j["nombre"].lower() == datos.nombre_jugador.lower() for j in sala["jugadores"])

    if nombre_existe:
        if sala["estado"] == "esperando_jugadores":
            raise HTTPException(status_code=400, detail="Ese nombre ya está en uso.")
        else:
            # Si la partida ya inició, permitimos reconectar
            return {"mensaje": f"Reconectando a {datos.nombre_jugador}..."}

    if sala["estado"] != "esperando_jugadores":
        raise HTTPException(status_code=400, detail="La partida ya comenzó o está cerrada.")

    # 2. datos del nuevo jugador
    nuevo_jugador = {
        "nombre": datos.nombre_jugador, 
        "rol": "por_asignar", 
        "vivo": True
    }
    
    await db.partidas.update_one(
        {"codigo_sala": datos.codigo_sala},
        {"$push": {"jugadores": nuevo_jugador}}
    )
    
    return {"mensaje": f"¡{datos.nombre_jugador} se ha unido a la sala {datos.codigo_sala}!"}
@app.get("/sala/{codigo_sala}")
async def obtener_sala(codigo_sala: str):
    sala = await db.partidas.find_one({"codigo_sala": codigo_sala})
    
    if not sala:
        raise HTTPException(status_code=404, detail="Sala no encontrada.")
        
    sala["_id"] = str(sala["_id"])
    
    return sala

@app.post("/iniciar-juego")
async def iniciar_juego(datos: IniciarJuegoRequest):
    sala = await db.partidas.find_one({"codigo_sala": datos.codigo_sala})
    
    if not sala:
        raise HTTPException(status_code=404, detail="Sala no encontrada.")
    if sala["estado"] != "esperando_jugadores":
        raise HTTPException(status_code=400, detail="La partida ya comenzó.")

    narrador = [j for j in sala["jugadores"] if j["rol"] == "narrador"][0]
    jugadores_activos = [j for j in sala["jugadores"] if j["rol"] != "narrador"]
    num_jugadores = len(jugadores_activos)

    # REGLA: De 8 a 11 jugadores = 2 Lobos. 12 o más = 3 Lobos.
    if num_jugadores >= 12:
        num_lobos = 3
    elif num_jugadores >= 8:
        num_lobos = 2
    else:
        num_lobos = 1

    # personajes especiales
    roles_baraja = ["Vidente", "Bruja", "Cupido", "Cazador", "Niña"]
    
    # Agregamos los Lobos 
    for _ in range(num_lobos):
        roles_baraja.append("Hombre Lobo")
        
    # Rellenamos con Aldeanos simples
    while len(roles_baraja) < num_jugadores:
        roles_baraja.append("Aldeano")
        
    roles_baraja = roles_baraja[:num_jugadores]

    # revolver las cartas de monse
    shuffle(roles_baraja)

    for i, jugador in enumerate(jugadores_activos):
        jugador["rol"] = roles_baraja[i]
        
        if jugador["rol"] == "Bruja":
            jugador["pocion_vida"] = True
            jugador["pocion_muerte"] = True
            
        jugador["enamorado"] = False
        jugador["alguacil"] = False

    lista_final_jugadores = [narrador] + jugadores_activos

  
    await db.partidas.update_one(
        {"codigo_sala": datos.codigo_sala},
        {
            "$set": {
                "estado": "turno_cupido",
                "jugadores": lista_final_jugadores,
                "ciclo": 1 
            }
        }
    )

    return {"mensaje": "Partida iniciada. Todos cierran los ojos. Es el turno de Cupido."}

@app.post("/narrador/avanzar")
async def narrador_avanzar(datos: NarradorAvanzarRequest):
    sala = await db.partidas.find_one({"codigo_sala": datos.codigo_sala})
    if not sala:
        raise HTTPException(status_code=404, detail="Sala no encontrada.")

    narrador = next((j for j in sala["jugadores"] if j["nombre"] == datos.nombre_narrador and j["rol"] == "narrador"), None)
    if not narrador:
        raise HTTPException(status_code=403, detail="No eres el Narrador.")

    jugadores = sala["jugadores"]
    estado_actual = sala["estado"]
    
    # 1. Obtenemos el ciclo para saber en qué noche estamos
    ciclo_actual = sala.get("ciclo", 1)

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

    es_cupido = False
    for j in jugadores:
        if j["nombre"] == datos.nombre_cupido and j["rol"] == "Cupido":
            es_cupido = True
            break
            
    if not es_cupido:
        raise HTTPException(status_code=403, detail="¡Trampa detectada! No eres Cupido.")

    
    if datos.enamorado_1 == datos.enamorado_2:
        raise HTTPException(status_code=400, detail="No puedes enamorar a la misma persona consigo misma.")

    for j in jugadores:
        if j["nombre"] == datos.enamorado_1 or j["nombre"] == datos.enamorado_2:
            j["enamorado"] = True
    
    siguiente_turno = calcular_siguiente_turno(jugadores, "turno_cupido")  

    await db.partidas.update_one(
        {"codigo_sala": datos.codigo_sala},
        {
            "$set": {
                "jugadores": jugadores,
                "estado": siguiente_turno
            }
        }
    )

    return {
        "mensaje": "Tus flechas han sido lanzadas con éxito.", 
        "estado_siguiente": siguiente_turno
    }


@app.post("/accion/vidente")
async def accion_vidente(datos: AccionVidenteRequest):
    sala = await db.partidas.find_one({"codigo_sala": datos.codigo_sala})
    
    if not sala:
        raise HTTPException(status_code=404, detail="Sala no encontrada.")
    if sala["estado"] != "turno_vidente":
        raise HTTPException(status_code=400, detail="Aún no es el turno de la Vidente.")

    jugadores = sala["jugadores"]
    es_vidente = any(j["nombre"] == datos.nombre_vidente and j["rol"] == "Vidente" for j in jugadores)
    
    if not es_vidente:
        raise HTTPException(status_code=403, detail="¡Trampa detectada! No eres la Vidente.")

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

    jugadores = sala["jugadores"]

    es_lobo_vivo = any(
        j["nombre"] == datos.nombre_lobo and j["rol"] == "Hombre Lobo" and j.get("vivo", True) 
        for j in jugadores
    )
    if not es_lobo_vivo:
        raise HTTPException(status_code=403, detail="No eres un Lobo o estás muerto.")

    votos_actuales = sala.get("votos_lobos", [])

    if any(v["lobo"] == datos.nombre_lobo for v in votos_actuales):
        raise HTTPException(status_code=400, detail="Ya emitiste tu voto esta noche.")

    votos_actuales.append({"lobo": datos.nombre_lobo, "voto": datos.nombre_objetivo})

    lobos_vivos = [j for j in jugadores if j["rol"] == "Hombre Lobo" and j.get("vivo", True)]
    total_lobos = len(lobos_vivos)

    if len(votos_actuales) < total_lobos:
        await db.partidas.update_one(
            {"codigo_sala": datos.codigo_sala},
            {"$set": {"votos_lobos": votos_actuales}}
        )
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
    await asyncio.sleep(3)

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

    lobos_vivos_count = sum(1 for j in jugadores if j["rol"] == "Hombre Lobo" and j.get("vivo", True))
    aldeanos_vivos_count = sum(1 for j in jugadores if j["rol"] not in ["Hombre Lobo", "narrador"] and j.get("vivo", True))

    if lobos_vivos_count == 0:
        estado_siguiente = "victoria_aldeanos"
    elif lobos_vivos_count >= aldeanos_vivos_count:
        estado_siguiente = "victoria_lobos"

    await db.partidas.update_one(
        {"codigo_sala": datos.codigo_sala},
        {
            "$set": {
                "estado": estado_siguiente,
                "jugadores": jugadores,
                "votos_lobos": [],
                "reporte_muertes": muertos_esta_noche
            }
        }
    )

    mensaje_final = "Todos los lobos han votado. "
    if hay_unanimidad:
        mensaje_final += "Hay consenso."
    else:
        mensaje_final += "No hubo unanimidad, la víctima se ha salvado."

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
    
    bruja = next((j for j in jugadores if j["nombre"] == datos.nombre_bruja and j["rol"] == "Bruja"), None)
    if not bruja or not bruja.get("vivo", True):
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

    lobos_vivos = sum(1 for j in jugadores if j["rol"] == "Hombre Lobo" and j.get("vivo", True))
    aldeanos_vivos = sum(1 for j in jugadores if j["rol"] not in ["Hombre Lobo", "narrador"] and j.get("vivo", True))
    
    if lobos_vivos == 0:
        estado_siguiente = "victoria_aldeanos"
    elif lobos_vivos >= aldeanos_vivos:
        estado_siguiente = "victoria_lobos"
        
    # 7. Amanece en el rancho (O termina el juego)
    await db.partidas.update_one(
        {"codigo_sala": datos.codigo_sala},
        {
            "$set": {
                "estado": estado_siguiente,
                "jugadores": jugadores,
                "reporte_muertes": list(muertos_esta_noche)
            },
            "$unset": {
                "victima_lobos": "" 
            }
        }
    )

    return {
        "mensaje": "Has mezclado tus pociones. La noche termina...",
        "estado_siguiente": estado_siguiente,
        "bajas_totales": list(muertos_esta_noche)
    }

@app.post("/accion/votar-dia")
async def votar_dia(datos: AccionVotoDiaRequest):
    # 1. Buscar la sala
    sala = await db.partidas.find_one({"codigo_sala": datos.codigo_sala})
    if not sala:
        raise HTTPException(status_code=404, detail="Sala no encontrada.")
    if sala["estado"] != "dia":
        raise HTTPException(status_code=400, detail="No es de día. No se puede votar.")

    jugadores = sala["jugadores"]

    # 2. Validar que existe y está VIVO
    votante = next((j for j in jugadores if j["nombre"] == datos.nombre_votante and j.get("vivo", True) and j["rol"] != "narrador"), None)
    if not votante:
        raise HTTPException(status_code=403, detail="No puedes votar. Estás muerto o no eres jugador.")

   
    votos_actuales = sala.get("votos_dia", [])
    
    if any(v["votante"] == datos.nombre_votante for v in votos_actuales):
        raise HTTPException(status_code=400, detail="Ya emitiste tu voto.")

    # Voto del Alguacil no implementado 
    peso_voto = 2 if votante.get("alguacil") else 1
    votos_actuales.append({
        "votante": datos.nombre_votante, 
        "acusado": datos.nombre_acusado,
        "peso": peso_voto
    })

    # 4. Verificar si ya votaron TODOS los vivos
    jugadores_vivos = [j for j in jugadores if j.get("vivo", True) and j["rol"] != "narrador"]
    
    if len(votos_actuales) < len(jugadores_vivos):
        # Aún faltan votos
        await db.partidas.update_one(
            {"codigo_sala": datos.codigo_sala},
            {"$set": {"votos_dia": votos_actuales}}
        )
        return {"mensaje": f"Voto registrado. Esperando a los demás... ({len(votos_actuales)}/{len(jugadores_vivos)})"}

    # 5. contar los votos
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
   
    lobos_vivos = sum(1 for j in jugadores if j["rol"] == "Hombre Lobo" and j.get("vivo", True))
    aldeanos_vivos = sum(1 for j in jugadores if j["rol"] not in ["Hombre Lobo", "narrador"] and j.get("vivo", True))
    
    if lobos_vivos == 0:
        estado_siguiente = "victoria_aldeanos"
    elif lobos_vivos >= aldeanos_vivos:
        estado_siguiente = "victoria_lobos"
        
    # 6. Actualiza la base de datos
    await db.partidas.update_one(
        {"codigo_sala": datos.codigo_sala},
        {
            "$set": {
                "estado": estado_siguiente,
                "jugadores": jugadores,
                "ultimo_linchado": list(muertos_por_linchamiento) if not hubo_empate else []
            },
            "$unset": {
                "votos_dia": "" # Vaciamos la urna
            }
        }
    )

    mensaje_final = "El pueblo ha hablado. "
    if hubo_empate:
        mensaje_final += "Nadie es linchado hoy."
    else:
        if estado_siguiente == "victoria_aldeanos":
            mensaje_final += "¡Los aldeanos han acabado con el último Lobo!"
        elif estado_siguiente == "victoria_lobos":
            mensaje_final += "¡Los Lobos ya son mayoría y devoran al resto del pueblo!"
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
    
    # 1. Validación de estado
    if sala["estado"] != "turno_cazador":
        raise HTTPException(status_code=400, detail="No es el turno del Cazador.")

    jugadores = sala["jugadores"]

    # 2. Encontrar al Cazador (el nombre debe coincidir con el rol)
    cazador = next((j for j in jugadores if j["nombre"] == datos.nombre_cazador and j["rol"] == "Cazador"), None)
    if not cazador:
        raise HTTPException(status_code=403, detail="No eres el Cazador.")

    # 3. Procesar el disparo si el objetivo existe y está vivo
    # Si el objetivo no es válido, podrías permitir que el turno avance sin disparo para no bloquear
    objetivo = next((j for j in jugadores if j["nombre"] == datos.nombre_objetivo), None)
    
    if objetivo and objetivo.get("vivo", True):
        # Aplicar muerte al objetivo
        for j in jugadores:
            if j["nombre"] == datos.nombre_objetivo:
                j["vivo"] = False
                
                # EFECTO DOMINÓ: Si el objetivo estaba enamorado, muere su pareja
                if j.get("enamorado"):
                    for pareja in jugadores:
                        if pareja.get("enamorado") and pareja["nombre"] != datos.nombre_objetivo and pareja.get("vivo", True):
                            pareja["vivo"] = False
    else:
        # Si el objetivo ya estaba muerto o no existe, lanzamos error para que elija bien
        # Pero asegúrate de que el frontend permita elegir objetivos válidos
        raise HTTPException(status_code=400, detail="Objetivo no válido o ya muerto.")

    # 4. Lógica de Victoria / Siguiente Turno
    # Verificamos si venimos de un linchamiento de día o una muerte de noche
    if sala.get("ultimo_linchado"):
        estado_siguiente = "esperando_narrador_noche"
    else:
        estado_siguiente = "dia"
    
    lobos_vivos = sum(1 for j in jugadores if j["rol"] == "Hombre Lobo" and j.get("vivo", True))
    aldeanos_vivos = sum(1 for j in jugadores if j["rol"] not in ["Hombre Lobo", "narrador"] and j.get("vivo", True))

    if lobos_vivos == 0:
        estado_siguiente = "victoria_aldeanos"
    elif lobos_vivos >= aldeanos_vivos:
        estado_siguiente = "victoria_lobos"

    # 5. Actualización final en la base de datos
    await db.partidas.update_one(
        {"codigo_sala": datos.codigo_sala},
        {
            "$set": {
                "estado": estado_siguiente,
                "jugadores": jugadores
            }
        }
    )

    return {
        "mensaje": f"El Cazador dispara su última bala a {datos.nombre_objetivo}.",
        "estado_siguiente": estado_siguiente
    }