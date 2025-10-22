import sqlite3
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import os
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
import datetime
from collections import defaultdict
import requests
import calendar

# Carrega as variáveis de ambiente do arquivo .env (para desenvolvimento local)
load_dotenv()

app = Flask(__name__, instance_relative_config=True)

# --- Configurações ---
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'uma_chave_secreta_padrao_para_teste_local_bem_longa')
API_KEY = os.environ.get('API_KEY')
MOEDAS_SUPORTADAS = ['BRL', 'USD', 'EUR', 'GBP']
CATEGORIAS_PADRAO = ["Alimentação", "Locomoção", "Casa", "Lazer", "Despesas inesperadas", "Parcelas/Crédito", "Outros/Indefinível"]
CATEGORIA_ABREVIACOES = {
    "Alimentação": "Alim", "Locomoção": "Locom", "Casa": "Casa", "Lazer": "Lazer", 
    "Despesas inesperadas": "Desp.In", "Parcelas/Crédito": "Parc.", "Outros/Indefinível": "Outro"
}


# --- Funções Auxiliares ---
def get_db_connection():
    db_path = os.path.join(app.instance_path, 'finance.db')
    os.makedirs(app.instance_path, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def obter_valor_convertido(valor_original, moeda_original):
    if moeda_original == 'BRL':
        return valor_original
    if not API_KEY or API_KEY == 'SUA_API_KEY_AQUI':
        print("AVISO: API Key não configurada. Usando valor original para conversão.")
        return valor_original
    try:
        url = f"https://v6.exchangerate-api.com/v6/{API_KEY}/pair/{moeda_original}/BRL"
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        dados_taxa = response.json()
        if dados_taxa.get('result') == 'success':
            taxa_conversao = dados_taxa['conversion_rate']
            return valor_original * taxa_conversao
    except requests.exceptions.RequestException as e:
        print(f"ERRO API: {e}")
    return valor_original

# --- ROTAS DE PÁGINAS (FRONTEND) ---

@app.route('/')
def index():
    if 'user_id' not in session: return redirect(url_for('login_page'))
    return render_template('index.html', moedas=MOEDAS_SUPORTADAS)

@app.route('/login')
def login_page():
    return render_template('login.html')

@app.route('/register')
def register_page():
    return render_template('register.html')

@app.route('/categorias')
def categorias_page():
    if 'user_id' not in session: return redirect(url_for('login_page'))
    return render_template('categorias.html')

# --- ROTAS DE LÓGICA (AUTH) ---

@app.route('/auth/login', methods=['POST', 'GET'])
def login_logic():
    if not request.is_json: return jsonify({"message": "Requisição deve ser JSON"}), 400
    data = request.get_json()
    username, password = data.get('username'), data.get('password')
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
    conn.close()
    if user and check_password_hash(user['password_hash'], password):
        session.clear()
        session['user_id'], session['username'] = user['id'], user['username']
        return jsonify({'success': True})
    return jsonify({'success': False, 'message': 'Usuário ou senha inválidos.'}), 401

@app.route('/auth/register', methods=['POST'])
def register_logic():
    if not request.is_json: return jsonify({"message": "Requisição deve ser JSON"}), 400
    data = request.get_json()
    username, password = data.get('username'), data.get('password')
    if not username or not password: return jsonify({'success': False, 'message': 'Usuário e senha são obrigatórios.'}), 400
    conn = get_db_connection()
    if conn.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone():
        conn.close()
        return jsonify({'success': False, 'message': f'Usuário "{username}" já existe.'}), 409
    password_hash = generate_password_hash(password)
    cursor = conn.cursor()
    cursor.execute('INSERT INTO users (username, password_hash) VALUES (?, ?)', (username, password_hash))
    user_id = cursor.lastrowid
    for categoria in CATEGORIAS_PADRAO:
        cursor.execute('INSERT INTO categorias (nome, user_id) VALUES (?, ?)', (categoria, user_id))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': 'Cadastro realizado com sucesso! Você será redirecionado para o login.'}), 201

@app.route('/auth/logout')
def logout():
    session.clear()
    return redirect(url_for('login_page'))

# --- API RESTful ---

@app.route('/api/session', methods=['GET'])
def get_session():
    if 'user_id' in session:
        return jsonify({'logged_in': True, 'user_id': session['user_id'], 'username': session['username']})
    return jsonify({'logged_in': False})

@app.route('/api/categorias', methods=['GET'])
def listar_categorias():
    if 'user_id' not in session: return jsonify({'erro': 'Não autorizado'}), 401
    conn = get_db_connection()
    categorias_db = conn.execute('SELECT * FROM categorias WHERE user_id = ? ORDER BY nome', (session['user_id'],)).fetchall()
    conn.close()
    return jsonify([dict(row) for row in categorias_db])

@app.route('/api/categorias', methods=['POST'])
def criar_categoria():
    if 'user_id' not in session: return jsonify({'erro': 'Não autorizado'}), 401
    data = request.get_json()
    if not data or not data.get('nome'): return jsonify({'erro': 'O nome da categoria é obrigatório.'}), 400
    nome = data['nome'].strip()
    if not nome: return jsonify({'erro': 'O nome da categoria não pode ser vazio.'}), 400
    user_id = session['user_id']
    conn = get_db_connection()
    existente = conn.execute('SELECT id FROM categorias WHERE nome = ? AND user_id = ?', (nome, user_id)).fetchone()
    if existente:
        conn.close()
        return jsonify({'erro': 'Esta categoria já existe.'}), 409
    cursor = conn.cursor()
    cursor.execute('INSERT INTO categorias (nome, user_id) VALUES (?, ?)', (nome, user_id))
    new_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return jsonify({'id': new_id, 'nome': nome, 'user_id': user_id}), 201

@app.route('/api/categorias/<int:id>', methods=['PUT'])
def atualizar_categoria(id):
    if 'user_id' not in session: return jsonify({'erro': 'Não autorizado'}), 401
    data = request.get_json()
    if not data or not data.get('nome'): return jsonify({'erro': 'O novo nome da categoria é obrigatório.'}), 400
    novo_nome, user_id = data['nome'].strip(), session['user_id']
    conn = get_db_connection()
    cat_original = conn.execute('SELECT * FROM categorias WHERE id = ? AND user_id = ?', (id, user_id)).fetchone()
    if not cat_original:
        conn.close()
        return jsonify({'erro': 'Categoria não encontrada ou não pertence a você.'}), 404
    nome_existente = conn.execute('SELECT id FROM categorias WHERE nome = ? AND user_id = ? AND id != ?', (novo_nome, user_id, id)).fetchone()
    if nome_existente:
        conn.close()
        return jsonify({'erro': 'Já existe outra categoria com este nome.'}), 409
    cursor = conn.cursor()
    cursor.execute('UPDATE categorias SET nome = ? WHERE id = ?', (novo_nome, id))
    conn.commit()
    conn.close()
    return jsonify({'id': id, 'nome': novo_nome, 'user_id': user_id})

@app.route('/api/categorias/<int:id>', methods=['DELETE'])
def deletar_categoria(id):
    if 'user_id' not in session: return jsonify({'erro': 'Não autorizado'}), 401
    user_id = session['user_id']
    conn = get_db_connection()
    gasto_usando = conn.execute('SELECT id FROM gastos WHERE categoria_id = ? AND user_id = ?', (id, user_id)).fetchone()
    if gasto_usando:
        conn.close()
        return jsonify({'erro': 'Não é possível excluir: categoria está sendo usada em um ou mais gastos.'}), 400
    cursor = conn.execute('DELETE FROM categorias WHERE id = ? AND user_id = ?', (id, user_id))
    conn.commit()
    conn.close()
    if cursor.rowcount == 0: return jsonify({'erro': 'Categoria não encontrada ou não pertence a você.'}), 404
    return '', 204

@app.route('/api/gastos', methods=['GET'])
def listar_gastos():
    if 'user_id' not in session: return jsonify({'erro': 'Não autorizado'}), 401
    user_id = session['user_id']
    ano = request.args.get('ano', default=datetime.datetime.now().year, type=int)
    mes = request.args.get('mes', default=datetime.datetime.now().month, type=int)
    conn = get_db_connection()
    query = "SELECT g.id, g.descricao, g.data, g.valor_original, g.moeda_original, g.valor_brl, g.info_parcela, g.categoria_id, c.nome as categoria_nome FROM gastos g JOIN categorias c ON g.categoria_id = c.id WHERE g.user_id = ?"
    params = [user_id]
    
    start_date = f'{ano}-{mes:02d}-01'
    _, num_days = calendar.monthrange(ano, mes)
    end_date = f'{ano}-{mes:02d}-{num_days}'
    query += " AND g.data BETWEEN ? AND ?"
    params.extend([start_date, end_date])
    
    query += " ORDER BY g.data DESC, g.id DESC"
    gastos_db = conn.execute(query, params).fetchall()
    conn.close()
    return jsonify([dict(gasto) for gasto in gastos_db])

@app.route('/api/gastos/<int:id>', methods=['GET'])
def obter_gasto(id):
    if 'user_id' not in session: return jsonify({'erro': 'Não autorizado'}), 401
    conn = get_db_connection()
    gasto = conn.execute('SELECT * FROM gastos WHERE id = ? AND user_id = ?', (id, session['user_id'])).fetchone()
    conn.close()
    if not gasto: return jsonify({'erro': 'Gasto não encontrado'}), 404
    return jsonify(dict(gasto))

@app.route('/api/gastos', methods=['POST'])
def criar_gasto():
    if 'user_id' not in session: return jsonify({'erro': 'Não autorizado'}), 401
    data = request.get_json()
    required = ['descricao', 'valor_original', 'moeda_original', 'categoria_id', 'data']
    if not all(field in data and data[field] not in [None, ''] for field in required): return jsonify({'erro': 'Campos obrigatórios ausentes'}), 400
    if not isinstance(data['valor_original'], (int, float)) or data['valor_original'] <= 0: return jsonify({'erro': 'O valor do gasto deve ser um número positivo'}), 400
    
    user_id = session['user_id']
    conn = get_db_connection()
    categoria = conn.execute('SELECT id, nome FROM categorias WHERE id = ? AND user_id = ?', (int(data['categoria_id']), user_id)).fetchone()
    if not categoria:
        conn.close()
        return jsonify({'erro': 'Categoria inválida'}), 400
    
    valor_brl = obter_valor_convertido(float(data['valor_original']), data['moeda_original'])
    
    info_parcela = None
    if categoria['nome'] == 'Parcelas/Crédito' and 'parcela_atual' in data and 'parcela_total' in data:
        info_parcela = f"{int(data['parcela_atual']):02d}/{int(data['parcela_total']):02d}"

    cursor = conn.cursor()
    cursor.execute('INSERT INTO gastos (descricao, data, valor_original, moeda_original, valor_brl, info_parcela, user_id, categoria_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                   (data['descricao'], data['data'], data['valor_original'], data['moeda_original'], valor_brl, info_parcela, user_id, data['categoria_id']))
    new_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    new_gasto_conn = get_db_connection()
    new_gasto = new_gasto_conn.execute('SELECT g.*, c.nome as categoria_nome FROM gastos g JOIN categorias c ON g.categoria_id = c.id WHERE g.id = ?', (new_id,)).fetchone()
    new_gasto_conn.close()
    return jsonify(dict(new_gasto)), 201

@app.route('/api/gastos/<int:id>', methods=['PUT'])
def atualizar_gasto(id):
    if 'user_id' not in session: return jsonify({'erro': 'Não autorizado'}), 401
    data = request.get_json()
    user_id = session['user_id']

    valor_brl = obter_valor_convertido(float(data['valor_original']), data['moeda_original'])
    
    info_parcela = None
    conn = get_db_connection()
    categoria = conn.execute('SELECT nome FROM categorias WHERE id = ? AND user_id = ?', (data['categoria_id'], user_id)).fetchone()
    if categoria and categoria['nome'] == 'Parcelas/Crédito' and 'parcela_atual' in data and 'parcela_total' in data:
        info_parcela = f"{int(data['parcela_atual']):02d}/{int(data['parcela_total']):02d}"
    
    cursor = conn.execute('UPDATE gastos SET descricao=?, data=?, valor_original=?, moeda_original=?, valor_brl=?, info_parcela=?, categoria_id=? WHERE id = ? AND user_id = ?',
                       (data['descricao'], data['data'], data['valor_original'], data['moeda_original'], valor_brl, info_parcela, data['categoria_id'], id, user_id))
    conn.commit()
    conn.close()

    if cursor.rowcount == 0: return jsonify({'erro': 'Gasto não encontrado ou não autorizado'}), 404
    
    updated_gasto_conn = get_db_connection()
    updated_gasto = updated_gasto_conn.execute('SELECT g.id, g.descricao, g.data, g.valor_original, g.moeda_original, g.valor_brl, g.info_parcela, c.nome as categoria_nome FROM gastos g JOIN categorias c ON g.categoria_id = c.id WHERE g.id = ?', (id,)).fetchone()
    updated_gasto_conn.close()
    return jsonify(dict(updated_gasto))

@app.route('/api/gastos/<int:id>', methods=['DELETE'])
def deletar_gasto(id):
    if 'user_id' not in session: return jsonify({'erro': 'Não autorizado'}), 401
    conn = get_db_connection()
    cursor = conn.execute('DELETE FROM gastos WHERE id = ? AND user_id = ?', (id, session['user_id']))
    conn.commit()
    conn.close()
    if cursor.rowcount == 0: return jsonify({'erro': 'Gasto não encontrado'}), 404
    return '', 204

@app.route('/api/reports/summary', methods=['GET'])
def get_summary():
    if 'user_id' not in session: return jsonify({'erro': 'Não autorizado'}), 401
    user_id = session['user_id']
    ano = request.args.get('ano', default=datetime.datetime.now().year, type=int)
    mes = request.args.get('mes', default=datetime.datetime.now().month, type=int)

    query = "SELECT c.nome as categoria_nome, SUM(g.valor_brl) as total FROM gastos g JOIN categorias c ON g.categoria_id = c.id WHERE g.user_id = ?"
    params = [user_id]
    
    start_date = f'{ano}-{mes:02d}-01'
    _, num_days = calendar.monthrange(ano, mes)
    end_date = f'{ano}-{mes:02d}-{num_days}'
    query += " AND g.data BETWEEN ? AND ?"
    params.extend([start_date, end_date])
    
    query += " GROUP BY c.nome"
    conn = get_db_connection()
    summary_db = conn.execute(query, params).fetchall()
    total_gasto = sum(row['total'] for row in summary_db)
    
    categorias_usuario = conn.execute('SELECT nome FROM categorias WHERE user_id = ?', (user_id,)).fetchall()
    
    gastos_por_categoria = {cat['nome']: 0.0 for cat in categorias_usuario}
    for row in summary_db:
        gastos_por_categoria[row['categoria_nome']] = row['total']
    
    grafico_data = []
    for cat_nome, total_cat in gastos_por_categoria.items():
        percentual = (total_cat / total_gasto) * 100 if total_gasto > 0 else 0
        abrev = CATEGORIA_ABREVIACOES.get(cat_nome, cat_nome[:4])
        grafico_data.append({
            "categoria_abrev": abrev,
            "valor_total": round(total_cat, 2),
            "percentual": round(percentual, 2)
        })

    conn.close()
    
    return jsonify({
        'total_gasto': total_gasto, 
        'grafico_data': grafico_data
    })


# --- Ponto de Partida ---
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)
