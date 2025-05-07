import os
from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'dev-secret-key')

# Configuração do Banco de Dados
uri = os.getenv('DATABASE_URL', 'sqlite:///checklist.db')
if uri and uri.startswith('postgres://'):
    uri = uri.replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = uri
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Modelos
class Usuario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    is_master = db.Column(db.Boolean, default=False)
    cavaleiro = db.relationship('Cavaleiro', backref='usuario', uselist=False)

class Cavaleiro(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(50), unique=True, nullable=False)
    classe = db.Column(db.String(20), default='Guerreiro')
    nivel = db.Column(db.Integer, default=1)
    experiencia = db.Column(db.Integer, default=0)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'))
    quests = db.relationship('Quest', backref='cavaleiro', lazy=True)
    conquistas = db.relationship('Conquista', backref='cavaleiro', lazy=True)

class Quest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    titulo = db.Column(db.String(200), nullable=False)
    descricao = db.Column(db.Text)
    concluida = db.Column(db.Boolean, default=False)
    diaria = db.Column(db.Boolean, default=False)
    semanal = db.Column(db.Boolean, default=False)
    global_quest = db.Column(db.Boolean, default=False)
    mestre_quest = db.Column(db.Boolean, default=False)
    categoria = db.Column(db.String(50))
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)
    cavaleiro_id = db.Column(db.Integer, db.ForeignKey('cavaleiro.id'))
    experiencia_recompensa = db.Column(db.Integer, default=10)

class Conquista(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    titulo = db.Column(db.String(200), nullable=False)
    descricao = db.Column(db.Text)
    data = db.Column(db.DateTime, default=datetime.utcnow)
    cavaleiro_id = db.Column(db.Integer, db.ForeignKey('cavaleiro.id'))
    global_conquista = db.Column(db.Boolean, default=False)

# Inicialização do banco de dados
with app.app_context():
    db.create_all()
    if not Usuario.query.filter_by(is_master=True).first():
        mestre = Usuario(
            username='mestre',
            password_hash=generate_password_hash('mestre123'),
            is_master=True
        )
        db.session.add(mestre)
        cavaleiro_mestre = Cavaleiro(
            nome='Mestre da Guilda',
            classe='Mestre',
            usuario_id=mestre.id
        )
        db.session.add(cavaleiro_mestre)
        db.session.commit()

# Agendador para resetar quests
def resetar_quests():
    with app.app_context():
        agora = datetime.utcnow()
        Quest.query.filter(
            Quest.diaria == True,
            Quest.concluida == True
        ).update({'concluida': False})
        
        if agora.weekday() == 6:  # Domingo
            Quest.query.filter(
                Quest.semanal == True,
                Quest.concluida == True
            ).update({'concluida': False})
        
        db.session.commit()

scheduler = BackgroundScheduler()
scheduler.add_job(resetar_quests, 'interval', hours=1)
scheduler.start()

# Rotas
@app.route('/')
def tabuleiro():
    if 'user_id' not in session:
        return render_template('login.html')
    
    cavaleiros = Cavaleiro.query.all()
    quests_globais = Quest.query.filter_by(global_quest=True).all()
    return render_template('tabuleiro.html',
                         cavaleiros=cavaleiros,
                         quests_globais=quests_globais,
                         is_master=is_master())

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = Usuario.query.filter_by(username=request.form['username']).first()
        if user and check_password_hash(user.password_hash, request.form['password']):
            session['user_id'] = user.id
            session['is_master'] = user.is_master
            return redirect(url_for('tabuleiro'))
        flash('Credenciais inválidas', 'error')
    return render_template('login.html')

@app.route('/registrar', methods=['GET', 'POST'])
def registrar():
    if request.method == 'POST':
        if Usuario.query.filter_by(username=request.form['username']).first():
            flash('Usuário já existe', 'error')
            return redirect(url_for('registrar'))
        
        novo_usuario = Usuario(
            username=request.form['username'],
            password_hash=generate_password_hash(request.form['password']),
            is_master=False
        )
        db.session.add(novo_usuario)
        db.session.commit()
        return redirect(url_for('login'))
    return render_template('registrar.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/cavaleiro/<int:cavaleiro_id>')
def perfil_cavaleiro(cavaleiro_id):
    cavaleiro = Cavaleiro.query.get_or_404(cavaleiro_id)
    quests = Quest.query.filter_by(cavaleiro_id=cavaleiro_id).all()
    conquistas = Conquista.query.filter_by(cavaleiro_id=cavaleiro_id).all()
    return render_template('perfil_cavaleiro.html',
                         cavaleiro=cavaleiro,
                         quests=quests,
                         conquistas=conquistas,
                         is_master=is_master())

@app.route('/conquistas')
def conquistas():
    conquistas = Conquista.query.filter_by(global_conquista=True).all()
    return render_template('conquistas.html',
                         conquistas=conquistas,
                         is_master=is_master())

@app.route('/adicionar_quest', methods=['POST'])
def adicionar_quest():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    nova_quest = Quest(
        titulo=request.form['titulo'],
        descricao=request.form['descricao'],
        diaria='diaria' in request.form,
        semanal='semanal' in request.form,
        global_quest='global_quest' in request.form and is_master(),
        mestre_quest='mestre_quest' in request.form and is_master(),
        categoria=request.form['categoria'],
        cavaleiro_id=request.form['cavaleiro_id'],
        experiencia_recompensa=int(request.form.get('experiencia_recompensa', 10))
    )
    db.session.add(nova_quest)
    db.session.commit()
    return redirect(url_for('perfil_cavaleiro', cavaleiro_id=request.form['cavaleiro_id']))

@app.route('/toggle_quest/<int:quest_id>')
def toggle_quest(quest_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    quest = Quest.query.get_or_404(quest_id)
    quest.concluida = not quest.concluida
    
    if quest.concluida and quest.cavaleiro_id:
        cavaleiro = Cavaleiro.query.get(quest.cavaleiro_id)
        cavaleiro.experiencia += quest.experiencia_recompensa
        if cavaleiro.experiencia >= cavaleiro.nivel * 100:
            cavaleiro.nivel += 1
            cavaleiro.experiencia = 0
            flash(f'{cavaleiro.nome} subiu para o nível {cavaleiro.nivel}!', 'success')
    
    db.session.commit()
    return redirect(request.referrer)

@app.route('/adicionar_conquista', methods=['POST'])
def adicionar_conquista():
    if 'user_id' not in session or not is_master():
        return redirect(url_for('login'))
    
    nova_conquista = Conquista(
        titulo=request.form['titulo'],
        descricao=request.form['descricao'],
        cavaleiro_id=request.form['cavaleiro_id'],
        global_conquista='global_conquista' in request.form
    )
    db.session.add(nova_conquista)
    db.session.commit()
    return redirect(url_for('perfil_cavaleiro', cavaleiro_id=request.form['cavaleiro_id']))

# Helper functions
def is_master():
    return 'is_master' in session and session['is_master']

if __name__ == '__main__':
    app.run(debug=True)