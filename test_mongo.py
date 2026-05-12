import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

# 1. Pega aquí el link que copiaste de la pantalla
MONGO_URL = "mongodb+srv://juego_admin:QaSVs2o7Q8uHwLA8@juego.yijg6sl.mongodb.net/?appName=Juego"

async def test_connection():
    print("🚀 Intentando conectar a MongoDB Atlas...")
    try:
        # Creamos el cliente
        client = AsyncIOMotorClient(MONGO_URL)
        
        # Intentamos obtener información del servidor para validar conexión
        info = await client.server_info()
        
        print("✅ ¡Conexión exitosa!")
        print(f"📡 Conectado a: {info.get('version')}")
        
        # Creamos un dato de prueba
        db = client.test_database
        collection = db.test_collection
        
        doc = {"proyecto": "Cancerbero", "estado": "Iniciado", "mensaje": "¡Hola desde la Mac!"}
        result = await collection.insert_one(doc)
        
        print(f"📝 Documento de prueba insertado con ID: {result.inserted_id}")
        
    except Exception as e:
        print(f"❌ Error de conexión: {e}")

if __name__ == "__main__":
    asyncio.run(test_connection())