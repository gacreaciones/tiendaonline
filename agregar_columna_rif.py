import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import app, db

def agregar_columna_rif():
    with app.app_context():
        try:
            # Agregar columna rif a la tabla cliente
            db.engine.
            print("Columna RIF agregada exitosamente")
        except Exception as e:
            print(f"Error al agregar columna: {e}")
            # Si falla, intentar con IF NOT EXISTS (dependiendo del gestor de BD)
            try:
                db.engine.execute('ALTER TABLE cliente ADD COLUMN IF NOT EXISTS rif VARCHAR(20)')
                print("Columna RIF verificada/agregada")
            except Exception as e2:
                print(f"Error alternativo: {e2}")

if __name__ == '__main__':
    agregar_columna_rif()