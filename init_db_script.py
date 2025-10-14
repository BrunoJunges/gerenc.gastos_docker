import sqlite3
import os
from werkzeug.security import generate_password_hash

print("--- EXECUTANDO SCRIPT DE INICIALIZAÇÃO DO BANCO DE DADOS (ARQUITETURA FINAL) ---")
DB_FILE = 'finance.db'

# Apaga o banco de dados antigo se ele existir, para garantir um recomeço limpo
if os.path.exists(DB_FILE):
    os.remove(DB_FILE)
    print(f"Banco de dados antigo '{DB_FILE}' removido.")

conn = None
try:
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # Tabela 1: Usuários
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL
        )
    ''')
    print("Tabela 'users' criada.")

    # Tabela 2: Categorias (com vínculo ao usuário)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS categorias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            UNIQUE(nome, user_id),
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    print("Tabela 'categorias' criada.")

    # Tabela 3: Gastos (com vínculo ao usuário e à categoria)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS gastos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            descricao TEXT NOT NULL,
            data TEXT NOT NULL,
            valor_original REAL NOT NULL,
            moeda_original TEXT NOT NULL,
            valor_brl REAL NOT NULL,
            info_parcela TEXT,
            user_id INTEGER NOT NULL,
            categoria_id INTEGER NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
            FOREIGN KEY (categoria_id) REFERENCES categorias (id) ON DELETE RESTRICT
        )
    ''')
    print("Tabela 'gastos' criada.")

    # Inserção de um usuário padrão para facilitar testes
    default_user = 'bruno'
    default_pass = '123'
    password_hash = generate_password_hash(default_pass)
    cursor.execute('INSERT INTO users (username, password_hash) VALUES (?, ?)', (default_user, password_hash))
    user_id = cursor.lastrowid
    print(f"Usuário padrão '{default_user}' criado com sucesso.")
    
    # Inserção de categorias padrão para o usuário padrão
    default_categorias = ["Alimentação", "Locomoção", "Casa", "Lazer", "Despesas inesperadas", "Parcelas/Crédito", "Outros/Indefinível"]
    for categoria in default_categorias:
        cursor.execute('INSERT INTO categorias (nome, user_id) VALUES (?, ?)', (categoria, user_id))
    print(f"Categorias padrão criadas para o usuário '{default_user}'.")

    conn.commit()
    print(f"\n--- SUCESSO: Banco de dados e dados iniciais criados em '{DB_FILE}'. ---")

except Exception as e:
    print(f"--- ERRO no script de inicialização: {e} ---")
    if conn:
        conn.rollback() # Desfaz qualquer mudança parcial
    exit(1)
finally:
    if conn:
        conn.close()