from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from flask_apscheduler import APScheduler
from datetime import datetime
import os

# Configurações
class Config:
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "sqlite:///checklist.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SCHEDULER_API_ENABLED = True
    SECRET_KEY = os.getenv("SECRET_KEY", "dev")

app = Flask(__name__)
app.config.from_object(Config)

db = SQLAlchemy(app)
scheduler = APScheduler()
scheduler.init_app(app)
scheduler.start()

# Constantes do jogo
CLASSES = ['Guerreiro', 'Mago', 'Arqueiro']
CATEGORIAS = ['Limpeza', 'Organização', 'Estudo', 'Saúde', 'Outro']

# Models
class Usuario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    senha = db.Column(db.String(100), nullable=False)
    master = db.Column(db.Boolean, default=False)

class Cavaleiro(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    classe = db.Column(db.String(50), nullable=False)
    experiencia = db.Column(db.Integer, default=0)
    nivel = db.Column(db.Integer, default=1)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)

class Quest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    titulo = db.Column(db.String(150), nullable=False)
    descricao = db.Column(db.Text, nullable=True)
    categoria = db.Column(db.String(50), nullable=False)
    concluida = db.Column(db.Boolean, default=False)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)
    cavaleiro_id = db.Column(db.Integer, db.ForeignKey('cavaleiro.id'), nullable=False)

class Conquista(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    descricao = db.Column(db.String(200))
    data = db.Column(db.DateTime, default=datetime.utcnow)
    cavaleiro_id = db.Column(db.Integer, db.ForeignKey('cavaleiro.id'), nullable=False)

# Utilitários
def usuario_logado():
    if "usuario_id" in session:
        return Usuario.query.get(session["usuario_id"])
    return None

def is_master():
    usuario = usuario_logado()
    return usuario and usuario.master

# Funções de jogo
def ganhar_experiencia(cavaleiro, pontos):
    cavaleiro.experiencia += pontos
    if cavaleiro.experiencia >= cavaleiro.nivel * 100:
        cavaleiro.nivel += 1
        cavaleiro.experiencia = 0
        conquista = Conquista(descricao=f"{cavaleiro.nome} subiu para o nível {cavaleiro.nivel}!", cavaleiro_id=cavaleiro.id)
        db.session.add(conquista)
    db.session.commit()

# Agendamento diário para resetar quests
@scheduler.task('cron', hour=0, minute=0)
def resetar_quests():
    quests = Quest.query.filter_by(concluida=True).all()
    for quest in quests:
        quest.concluida = False
    db.session.commit()

# Rotas
@app.route('/')
def index():
    if not usuario_logado():
        return redirect(url_for('login'))
    return redirect(url_for('tabuleiro'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        senha = request.form['senha']
        usuario = Usuario.query.filter_by(email=email, senha=senha).first()
        if usuario:
            session['usuario_id'] = usuario.id
            return redirect(url_for('tabuleiro'))
        flash('Credenciais inválidas', 'error')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/tabuleiro')
def tabuleiro():
    usuario = usuario_logado()
    if not usuario:
        return redirect(url_for('login'))
    cavaleiros = Cavaleiro.query.filter_by(usuario_id=usuario.id).all() if not usuario.master else Cavaleiro.query.all()
    return render_template('tabuleiro.html', cavaleiros=cavaleiros, usuario_logado=usuario, is_master=is_master())

@app.route('/cavaleiro/<int:cavaleiro_id>', methods=['GET', 'POST'])
def perfil_cavaleiro(cavaleiro_id):
    try:
        cavaleiro = Cavaleiro.query.get_or_404(cavaleiro_id)
        if request.method == 'POST':
            titulo = request.form['titulo']
            categoria = request.form['categoria']
            nova_quest = Quest(titulo=titulo, categoria=categoria, cavaleiro_id=cavaleiro.id)
            db.session.add(nova_quest)
            db.session.commit()
            return redirect(url_for('perfil_cavaleiro', cavaleiro_id=cavaleiro.id))
        
        quests = Quest.query.filter_by(cavaleiro_id=cavaleiro.id).all()
        conquistas = Conquista.query.filter_by(cavaleiro_id=cavaleiro.id).order_by(Conquista.data.desc()).all()
        
        return render_template('perfil_cavaleiro.html',
                               cavaleiro=cavaleiro,
                               quests=quests,
                               conquistas=conquistas,
                               classes=CLASSES,
                               categorias=CATEGORIAS,
                               usuario_logado=usuario_logado(),
                               is_master=is_master())
    except Exception as e:
        flash('Erro ao carregar perfil do cavaleiro', 'error')
        return redirect(url_for('tabuleiro'))

@app.route('/quest/<int:quest_id>/concluir')
def concluir_quest(quest_id):
    quest = Quest.query.get_or_404(quest_id)
    quest.concluida = True
    ganhar_experiencia(quest.cavaleiro, 50)
    db.session.commit()
    return redirect(url_for('perfil_cavaleiro', cavaleiro_id=quest.cavaleiro_id))

# Execução
if __name__ == '__main__':
    db.create_all()
    app.run(debug=True)
