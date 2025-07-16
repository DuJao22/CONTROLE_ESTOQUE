import sqlite3
import sqlitecloud  # biblioteca do SQLiteCloud
from flask import Flask, render_template, request, redirect, url_for, session, flash, g
from datetime import datetime
import os

app = Flask(__name__)
app.secret_key = 'controle_estoque_clinicas_2024'

# URL do SQLiteCloud
DATABASE_URL = 'sqlitecloud://cmq6frwshz.g4.sqlite.cloud:8860/estoque.db?apikey=Dor8OwUECYmrbcS5vWfsdGpjCpdm9ecSDJtywgvRw8k'

# Função personalizada para retornar linhas como dicionário
def dict_factory(cursor, row):
    return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}

# Função para conectar ao SQLiteCloud
def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlitecloud.connect(DATABASE_URL)
        db.row_factory = dict_factory
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def init_db():
    with app.app_context():
        db = get_db()
        db.executescript('''
            CREATE TABLE IF NOT EXISTS usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL,
                login TEXT UNIQUE NOT NULL,
                senha TEXT NOT NULL,
                tipo TEXT NOT NULL,
                clinica TEXT
            );
            
            CREATE TABLE IF NOT EXISTS produtos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL,
                descricao TEXT,
                quantidade_atual INTEGER DEFAULT 0,
                quantidade_minima INTEGER DEFAULT 0,
                clinica TEXT NOT NULL,
                data_criacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            
            CREATE TABLE IF NOT EXISTS retiradas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                produto_id INTEGER,
                produto_nome TEXT,
                quantidade INTEGER,
                usuario_nome TEXT,
                clinica TEXT,
                data_retirada TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (produto_id) REFERENCES produtos (id)
            );

            INSERT OR IGNORE INTO usuarios (nome, login, senha, tipo, clinica) VALUES
            ('Administrador', 'admin', 'admin123', 'admin', NULL),
            ('Funcionário BH', 'funcbh', 'func123', 'funcionario', 'BH'),
            ('Funcionário Contagem', 'funccontagem', 'func123', 'funcionario', 'Contagem');
        ''')
        db.commit()

@app.route('/')
def index():
    if 'usuario_id' in session:
        if session['tipo'] == 'admin':
            return redirect(url_for('admin_dashboard'))
        else:
            return redirect(url_for('func_dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        login_usuario = request.form['login']
        senha = request.form['senha']

        db = get_db()
        usuario = db.execute(
            'SELECT * FROM usuarios WHERE login = ? AND senha = ?',
            (login_usuario, senha)
        ).fetchone()

        if usuario:
            session['usuario_id'] = usuario['id']
            session['usuario_nome'] = usuario['nome']
            session['tipo'] = usuario['tipo']
            session['clinica'] = usuario['clinica']
            flash('Login realizado com sucesso!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Login ou senha inválidos!', 'error')

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Logout realizado com sucesso!', 'success')
    return redirect(url_for('login'))

@app.route('/admin/dashboard')
def admin_dashboard():
    if 'usuario_id' not in session or session['tipo'] != 'admin':
        flash('Acesso negado!', 'error')
        return redirect(url_for('login'))

    db = get_db()
    produtos_bh = db.execute(
        'SELECT * FROM produtos WHERE clinica = "BH" ORDER BY nome'
    ).fetchall()
    produtos_bh_baixo = db.execute(
        'SELECT * FROM produtos WHERE clinica = "BH" AND quantidade_atual <= quantidade_minima ORDER BY nome'
    ).fetchall()
    produtos_contagem = db.execute(
        'SELECT * FROM produtos WHERE clinica = "Contagem" ORDER BY nome'
    ).fetchall()
    produtos_contagem_baixo = db.execute(
        'SELECT * FROM produtos WHERE clinica = "Contagem" AND quantidade_atual <= quantidade_minima ORDER BY nome'
    ).fetchall()

    return render_template('admin_dashboard.html', 
                         produtos_bh=produtos_bh,
                         produtos_bh_baixo=produtos_bh_baixo,
                         produtos_contagem=produtos_contagem,
                         produtos_contagem_baixo=produtos_contagem_baixo)

@app.route('/funcionario/dashboard')
def func_dashboard():
    if 'usuario_id' not in session or session['tipo'] != 'funcionario':
        flash('Acesso negado!', 'error')
        return redirect(url_for('login'))

    db = get_db()
    produtos = db.execute(
        'SELECT * FROM produtos WHERE clinica = ? ORDER BY nome',
        (session['clinica'],)
    ).fetchall()

    return render_template('func_dashboard.html', 
                         produtos=produtos, 
                         clinica=session['clinica'])

@app.route('/admin/cadastro-produto', methods=['GET', 'POST'])
def cadastro_produto():
    if 'usuario_id' not in session or session['tipo'] != 'admin':
        flash('Acesso negado!', 'error')
        return redirect(url_for('login'))

    if request.method == 'POST':
        nome = request.form['nome']
        descricao = request.form['descricao']
        quantidade_atual = int(request.form['quantidade_atual'])
        quantidade_minima = int(request.form['quantidade_minima'])
        clinica = request.form['clinica']

        db = get_db()
        db.execute('''
            INSERT INTO produtos (nome, descricao, quantidade_atual, quantidade_minima, clinica)
            VALUES (?, ?, ?, ?, ?)
        ''', (nome, descricao, quantidade_atual, quantidade_minima, clinica))
        db.commit()

        flash(f'Produto cadastrado com sucesso na clínica {clinica}!', 'success')
        return redirect(url_for('admin_dashboard'))

    return render_template('cadastro_produto.html')

@app.route('/funcionario/retirar-produto/<int:produto_id>', methods=['GET', 'POST'])
def retirar_produto(produto_id):
    if 'usuario_id' not in session or session['tipo'] != 'funcionario':
        flash('Acesso negado!', 'error')
        return redirect(url_for('login'))

    db = get_db()
    produto = db.execute(
        'SELECT * FROM produtos WHERE id = ? AND clinica = ?', 
        (produto_id, session['clinica'])
    ).fetchone()

    if not produto:
        flash('Produto não encontrado ou não pertence à sua clínica!', 'error')
        return redirect(url_for('func_dashboard'))

    if request.method == 'POST':
        quantidade_retirada = int(request.form['quantidade'])

        if quantidade_retirada > produto['quantidade_atual']:
            flash('Quantidade indisponível no estoque!', 'error')
            return render_template('retirar_produto.html', produto=produto)

        nova_quantidade = produto['quantidade_atual'] - quantidade_retirada

        db.execute('UPDATE produtos SET quantidade_atual = ? WHERE id = ?', 
                  (nova_quantidade, produto_id))

        db.execute('''
            INSERT INTO retiradas (produto_id, produto_nome, quantidade, usuario_nome, clinica)
            VALUES (?, ?, ?, ?, ?)
        ''', (produto_id, produto['nome'], quantidade_retirada, session['usuario_nome'], session['clinica']))

        db.commit()

        flash(f'Retirada de {quantidade_retirada} unidades de "{produto["nome"]}" realizada com sucesso!', 'success')
        return redirect(url_for('func_dashboard'))

    return render_template('retirar_produto.html', produto=produto)

@app.route('/admin/historico-retiradas')
def historico_retiradas():
    if 'usuario_id' not in session or session['tipo'] != 'admin':
        flash('Acesso negado!', 'error')
        return redirect(url_for('login'))

    db = get_db()
    retiradas_bh = db.execute('''
        SELECT * FROM retiradas 
        WHERE clinica = "BH" 
        ORDER BY data_retirada DESC
        LIMIT 50
    ''').fetchall()

    retiradas_contagem = db.execute('''
        SELECT * FROM retiradas 
        WHERE clinica = "Contagem" 
        ORDER BY data_retirada DESC
        LIMIT 50
    ''').fetchall()

    return render_template('historico_retiradas.html', 
                         retiradas_bh=retiradas_bh,
                         retiradas_contagem=retiradas_contagem)

if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='0.0.0.0', port=5000)
