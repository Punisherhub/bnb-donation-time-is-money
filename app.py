# app.py - Versão corrigida para doações de BNB na BSC
import base64
import io
import os
import sqlite3
from datetime import datetime, timedelta
from threading import Lock

import qrcode
from flask import Flask, jsonify, render_template, request
from flask_cors import CORS

# --- Configuração ---
app = Flask(__name__)
CORS(app)

# Endereço de destino da sua carteira
BSC_ADDRESS = "0xd5d16f8A035fc52F4a93890D52Ca58004CF6E9B0"
# Chain ID da BNB Smart Chain
BSC_CHAIN_ID = 56

# Configuração do caminho do banco de dados
if os.environ.get('RENDER'):
    # No Render, usa o disco persistente
    DATABASE_PATH = "/opt/render/project/data/donations_bnb.db"
    os.makedirs("/opt/render/project/data", exist_ok=True)
else:
    # Desenvolvimento local
    DATABASE_PATH = "donations_bnb.db"
db_lock = Lock()

# --- Funções do Banco de Dados ---
def init_database():
    """Inicializa o banco de dados para rastrear doações de BNB."""
    with db_lock:
        with sqlite3.connect(DATABASE_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS donations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    crypto_type TEXT NOT NULL DEFAULT 'BNB',
                    amount REAL NOT NULL,
                    transaction_hash TEXT UNIQUE NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            # Adiciona dados de exemplo se o banco estiver vazio
            cursor.execute("SELECT COUNT(*) FROM donations")
            if cursor.fetchone()[0] == 0:
                print("Database is empty. Populating with sample BNB donations...")
                sample_donations = [
                    ('BNB', 0.05, 'sample_tx_1_bnb', datetime.now() - timedelta(hours=1)),
                    ('BNB', 0.02, 'sample_tx_2_bnb', datetime.now() - timedelta(hours=3)),
                    ('BNB', 0.1, 'sample_tx_3_bnb', datetime.now() - timedelta(days=1))
                ]
                for donation in sample_donations:
                    cursor.execute('INSERT INTO donations (crypto_type, amount, transaction_hash, timestamp) VALUES (?, ?, ?, ?)', donation)
                conn.commit()
            print("Database initialized successfully.")

def get_db_connection():
    """Obtém uma conexão com o banco de dados."""
    conn = sqlite3.connect(DATABASE_PATH, detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES)
    conn.row_factory = sqlite3.Row
    return conn

# --- Função Utilitária ---
def generate_qr_code(data):
    """Gera uma imagem de QR Code e a retorna como string base64."""
    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=10, border=4)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)
    return base64.b64encode(buffer.getvalue()).decode()

# --- Endpoints da API ---
@app.route('/')
def index():
    """Serve a página principal index.html."""
    return render_template('index.html')

@app.route('/api/crypto-info')
def crypto_info():
    """Fornece as informações de doação para BNB na rede BEP20."""
    try:
        # Formato EIP-681 para a moeda nativa da chain
        payment_link = f"ethereum:{BSC_ADDRESS}@{BSC_CHAIN_ID}"
        
        qr_code_base64 = generate_qr_code(payment_link)
        
        return jsonify({
            'address': BSC_ADDRESS,
            'network': 'BNB Smart Chain',
            'token': 'BNB',
            'qr_code': f"data:image/png;base64,{qr_code_base64}",
            'payment_link': payment_link
        })
    except Exception as e:
        print(f"Error in crypto_info: {str(e)}")
        return jsonify({'error': 'Failed to generate crypto info'}), 500

@app.route('/api/stats')
def get_stats():
    """Obtém estatísticas de doações de BNB do banco de dados."""
    try:
        with db_lock:
            conn = get_db_connection()
            
            # Pega o total de BNB doado
            total_bnb = conn.execute("SELECT COALESCE(SUM(amount), 0) as total FROM donations").fetchone()['total']
            
            # Pega o total de doações
            total_donations = conn.execute("SELECT COUNT(*) as count FROM donations").fetchone()['count']
            
            # Pega as doações recentes com timestamp como datetime
            recent_donations_raw = conn.execute("""
                SELECT amount, timestamp as "timestamp [timestamp]"
                FROM donations 
                ORDER BY timestamp DESC 
                LIMIT 3
            """).fetchall()
            
            conn.close()

        recent_donations = []
        for donation in recent_donations_raw:
            # Agora donation['timestamp'] é um objeto datetime
            time_diff = datetime.now() - donation['timestamp']
            
            if time_diff.days > 0:
                time_ago = f"{time_diff.days}d ago"
            elif time_diff.seconds >= 3600:
                hours = time_diff.seconds // 3600
                time_ago = f"{hours}h ago"
            elif time_diff.seconds >= 60:
                minutes = time_diff.seconds // 60
                time_ago = f"{minutes}m ago"
            else:
                time_ago = "just now"
                
            recent_donations.append({
                'amount': f"{donation['amount']:.4f} BNB",
                'time': time_ago
            })

        return jsonify({
            'total_donations': total_donations,
            'total_amount_bnb': round(total_bnb, 4),
            'recent_donations': recent_donations
        })
        
    except Exception as e:
        print(f"Error in get_stats: {str(e)}")
        return jsonify({
            'total_donations': 0,
            'total_amount_bnb': 0,
            'recent_donations': []
        }), 500

# --- Execução Principal ---
if __name__ == '__main__':
    # Garante que o banco de dados seja inicializado
    if not os.path.exists(DATABASE_PATH):
        print(f"Creating database at {DATABASE_PATH}")
        init_database()
    else:
        # Verifica se o banco tem a estrutura correta
        try:
            conn = get_db_connection()
            conn.execute("SELECT 1 FROM donations LIMIT 1")
            conn.close()
            print("Database exists and is properly structured.")
        except sqlite3.OperationalError:
            print("Database exists but needs initialization.")
            os.remove(DATABASE_PATH)
            init_database()
    
    # Configuração para produção
    port = int(os.environ.get('PORT', 8000))
    debug_mode = os.environ.get('RENDER') is None  # Debug apenas local
    
    app.run(debug=debug_mode, host='0.0.0.0', port=port)