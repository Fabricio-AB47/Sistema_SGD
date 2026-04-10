"""
Ejecutar script SQL para crear tablas de jerarquía institucional
"""
import os
import sys
import django
from pathlib import Path

# Configurar Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'SIG.settings')
django.setup()

from django.db import connection

# Leer el script SQL
script_path = Path(__file__).parent / 'create_hierarchy_tables.sql'
with open(script_path, 'r', encoding='utf-8') as f:
    sql_content = f.read()

# Ejecutar el script
try:
    with connection.cursor() as cursor:
        # Dividir por GO y ejecutar cada bloque
        for statement in sql_content.split('GO'):
            stmt = statement.strip()
            if stmt and not stmt.startswith('--'):
                print(f"Ejecutando: {stmt[:60]}...")
                cursor.execute(stmt)
    
    print("\n✓ Tablas creadas exitosamente")
    
except Exception as e:
    print(f"\n✗ Error: {e}")
    sys.exit(1)
