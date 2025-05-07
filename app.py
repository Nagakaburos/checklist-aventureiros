import os
from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'dev-secret-key')
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif'}

# Configuração do Banco de Dados
uri = os.getenv('DATABASE_URL')
if uri and uri.startswith('postgres://'):
    uri = uri.replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = uri or 'sqlite:///checklist.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_pre_ping': True,
    'pool_recycle': 300
}

db = SQLAlchemy(app)
migrate = Migrate(app, db)  # Adicionando suporte a migrações

CLASSES = {
    'Guerreiro': {'icone': '⚔️', 'cor_primaria': '#8B0000', 'cor_secundaria': '#C5B358'},
    'Mago': {'icone': '🔮', 'cor_primaria': '#4B0082', 'cor_secundaria': '#ADD8E6'},
    'Arqueiro': {'icone': '🏹', 'cor_primaria': '#556B2F', 'cor_secundaria': '#F0E68C'},
    'Ladino': {'icone': '🗡️', 'cor_primaria': '#2F4F4F', 'cor_secundaria': '#708090'},
    'Clérigo': {'icone': '🙏', 'cor_primaria': '#FFD700', 'cor_secundaria': '#FFFFFF'},
    'Necromante': {'icone': '💀', 'cor_primaria': '#228B22', 'cor_secundaria': '#000000'},
    'Mestre': {'icone': '👑', 'cor_primaria': '#800080', 'cor_secundaria': '#FFD700'}
}

CATEGORIAS = [
    ('manha', '🌄 Manhã'),
    ('dia', '🏰 Durante o Dia'),
    ('instagram_stories', '📜 Instagram/Stories'),
    ('instagram_feed', '📜 Instagram/Feed'),
    ('instagram_perguntas', '📜 Instagram/Perguntas'),
    ('whatsapp_status', '📯 WhatsApp/Status'),
    ('whatsapp_transmissao', '📯 WhatsApp/Transmissão'),
    ('vendas', '💰 Vendas'),
    ('pos_venda', '📦 Pós-Venda'),
    ('parcerias', '🤝 Parcerias'),
    ('expediente', '🌙 Fim de Expediente')
]

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
    imagem = db.Column(db.String(100))
    nivel = db.Column(db.Integer, default=1)
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
    ultima_conclusao = db.Column(db.DateTime)
    desativada_ate = db.Column(db.DateTime)
    cavaleiro_id = db.Column(db.Integer, db.ForeignKey('cavaleiro.id'))
    concluida_por = db.Column(db.String(50))

class Conquista(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    titulo = db.Column(db.String(200), nullable=False)
    descricao = db.Column(db.Text)
    data = db.Column(db.DateTime, default=datetime.utcnow)
    cavaleiro_id = db.Column(db.Integer, db.ForeignKey('cavaleiro.id'))
    autor_nome = db.Column(db.String(50), default='Aventureiro')
    global_conquista = db.Column(db.Boolean, default=False)  # Coluna corrigida

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def criar_tabelas():
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

criar_tabelas()

def resetar_quests():
    with app.app_context():
        agora = datetime.utcnow()
        
        # Resetar quests diárias
        Quest.query.filter(
            Quest.diaria == True,
            Quest.desativada_ate <= agora
        ).update({
            'concluida': False,
            'desativada_ate': None,
            'concluida_por': None
        })
        
        # Resetar quests semanais (domingo)
        if agora.weekday() == 6:
            Quest.query.filter(
                Quest.semanal == True,
                Quest.desativada_ate <= agora
            ).update({
                'concluida': False,
                'desativada_ate': None,
                'concluida_por': None
            })
        
        db.session.commit()

if not app.debug or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
    scheduler = BackgroundScheduler()
    scheduler.add_job(resetar_quests, 'interval', hours=1)
    scheduler.start()

def usuario_logado():
    return Usuario.query.get(session.get('user_id'))

def is_master():
    user = usuario_logado()
    return user and user.is_master

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = Usuario.query.filter_by(username=request.form['username']).first()
        if user and check_password_hash(user.password_hash, request.form['password']):
            session['user_id'] = user.id
            session['is_master'] = user.is_master
            if user.cavaleiro:
                session['cavaleiro_id'] = user.cavaleiro.id
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

@app.before_request
def requer_login():
    if request.endpoint not in ['login', 'registrar', 'static', 'tabuleiro', 'conquistas'] and 'user_id' not in session:
        return redirect(url_for('login'))

@app.route('/')
def tabuleiro():
    conquistas_globais = Conquista.query.filter_by(global_conquista=True).order_by(Conquista.data.desc()).limit(5).all()
    cavaleiros = Cavaleiro.query.all()
    quests_globais = Quest.query.filter_by(global_quest=True).all()
    return render_template('tabuleiro.html',
                        cavaleiros=cavaleiros,
                        classes=CLASSES,
                        conquistas=conquistas_globais,
                        categorias=CATEGORIAS,
                        quests_globais=quests_globais,
                        is_master=is_master(),
                        usuario_logado=usuario_logado())

@app.route('/cavaleiro/<int:cavaleiro_id>')
def perfil_cavaleiro(cavaleiro_id):
    cavaleiro = Cavaleiro.query.get_or_404(cavaleiro_id)
    quests = Quest.query.filter_by(cavaleiro_id=cavaleiro_id, global_quest=False).all()
    conquistas = Conquista.query.filter_by(cavaleiro_id=cavaleiro_id).all()
    return render_template('perfil_cavaleiro.html',
                        cavaleiro=cavaleiro,
                        classes=CLASSES,
                        quests=quests,
                        conquistas=conquistas,
                        categorias=CATEGORIAS,
                        is_master=is_master(),
                        usuario_logado=usuario_logado())

@app.route('/adicionar_cavaleiro', methods=['POST'])
def adicionar_cavaleiro():
    if not usuario_logado():
        flash('Ação requer login', 'error')
        return redirect(url_for('login'))
    
    try:
        imagem = None
        if 'imagem' in request.files:
            file = request.files['imagem']
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                imagem = filename

        novo_cavaleiro = Cavaleiro(
            nome=request.form['nome'],
            classe=request.form['classe'],
            imagem=imagem,
            usuario_id=usuario_logado().id
        )
        db.session.add(novo_cavaleiro)
        db.session.commit()
        flash('Cavaleiro criado!', 'success')
    except Exception as e:
        flash(f'Erro: {str(e)}', 'error')
        db.session.rollback()
    return redirect(url_for('tabuleiro'))

@app.route('/adicionar_quest', methods=['POST'])
def adicionar_quest():
    if not usuario_logado():
        flash('Ação requer login', 'error')
        return redirect(url_for('login'))
    
    try:
        nova_quest = Quest(
            titulo=request.form['titulo'],
            descricao=request.form['descricao'],
            diaria='diaria' in request.form,
            semanal='semanal' in request.form,
            global_quest='global_quest' in request.form and is_master(),
            mestre_quest='mestre_quest' in request.form and is_master(),
            categoria=request.form['categoria'],
            cavaleiro_id=request.form['cavaleiro_id']
        )
        db.session.add(nova_quest)
        db.session.commit()
        flash('Missão adicionada!', 'success')
    except Exception as e:
        flash(f'Erro: {str(e)}', 'error')
        db.session.rollback()
    
    return redirect(url_for('perfil_cavaleiro', cavaleiro_id=request.form['cavaleiro_id']))

@app.route('/toggle_quest/<int:quest_id>')
def toggle_quest(quest_id):
    if not usuario_logado():
        flash('Ação requer login', 'error')
        return redirect(url_for('login'))
    
    quest = Quest.query.get_or_404(quest_id)
    user = usuario_logado()
    
    if not (quest.global_quest or (user.cavaleiro and quest.cavaleiro_id == user.cavaleiro.id) or is_master()):
        flash('Permissão negada', 'error')
        return redirect(url_for('tabuleiro'))
    
    if quest.mestre_quest and quest.concluida:
        flash('Missões do Mestre não podem ser desfeitas', 'error')
        return redirect(request.referrer)
    
    try:
        quest.concluida = not quest.concluida
        quest.ultima_conclusao = datetime.utcnow() if quest.concluida else None
        quest.concluida_por = user.cavaleiro.nome if quest.concluida else None
        
        if quest.mestre_quest and quest.concluida:
            cavaleiro = Cavaleiro.query.get(quest.cavaleiro_id)
            cavaleiro.nivel += 1
            flash(f'Nível aumentado para {cavaleiro.nivel}!', 'success')
        
        db.session.commit()
    except Exception as e:
        flash(f'Erro: {str(e)}', 'error')
        db.session.rollback()
    
    return redirect(request.referrer)

@app.route('/adicionar_conquista', methods=['POST'])
def adicionar_conquista():
    if not usuario_logado():
        flash('Ação requer login', 'error')
        return redirect(url_for('login'))
    
    try:
        nova_conquista = Conquista(
            titulo=request.form['titulo'],
            descricao=request.form['descricao'],
            cavaleiro_id=request.form['cavaleiro_id'],
            global_conquista='global_conquista' in request.form and is_master()
        )
        db.session.add(nova_conquista)
        db.session.commit()
        flash('Conquista adicionada!', 'success')
    except Exception as e:
        flash(f'Erro: {str(e)}', 'error')
        db.session.rollback()
    
    return redirect(url_for('perfil_cavaleiro', cavaleiro_id=request.form['cavaleiro_id']))

@app.route('/conquistas')
def conquistas():
    conquistas = Conquista.query.filter_by(global_conquista=True).order_by(Conquista.data.desc()).all()
    return render_template('conquistas.html',
                        conquistas=conquistas,
                        classes=CLASSES,
                        is_master=is_master(),
                        usuario_logado=usuario_logado())

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)