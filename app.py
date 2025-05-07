import os
from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from werkzeug.security import generate_password_hash, check_password_hash

# Inicialização do Flask
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'dev-secret-key')

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

# Constantes
CLASSES = {
    'Guerreiro': {'icone': '⚔️', 'cor_primaria': '#8B0000', 'cor_secundaria': '#C5B358'},
    'Mago': {'icone': '🔮', 'cor_primaria': '#4B0082', 'cor_secundaria': '#ADD8E6'},
    'Arqueiro': {'icone': '🏹', 'cor_primaria': '#556B2F', 'cor_secundaria': '#F0E68C'},
    'Ladino': {'icone': '🗡️', 'cor_primaria': '#2F4F4F', 'cor_secundaria': '#708090'},
    'Clérigo': {'icone': '🙏', 'cor_primaria': '#FFD700', 'cor_secundaria': '#FFFFFF'},
    'Necromante': {'icone': '💀', 'cor_primaria': '#228B22', 'cor_secundaria': '#000000'}
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
    quests = db.relationship('Quest', backref='cavaleiro', lazy=True)
    conquistas = db.relationship('Conquista', backref='cavaleiro', lazy=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'))

class Quest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    titulo = db.Column(db.String(200), nullable=False)
    descricao = db.Column(db.Text)
    concluida = db.Column(db.Boolean, default=False)
    diaria = db.Column(db.Boolean, default=False)
    semanal = db.Column(db.Boolean, default=False)
    global_quest = db.Column(db.Boolean, default=False)
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

# Inicialização do Banco
def criar_tabelas():
    with app.app_context():
        try:
            db.create_all()
            
            # Criar usuário mestre padrão se não existir
            if not Usuario.query.filter_by(is_master=True).first():
                mestre = Usuario(
                    username='mestre',
                    password_hash=generate_password_hash('mestre123'),
                    is_master=True
                )
                db.session.add(mestre)
                db.session.commit()
                
                cavaleiro_mestre = Cavaleiro(
                    nome='Mestre da Guilda',
                    classe='Mago',
                    usuario_id=mestre.id
                )
                db.session.add(cavaleiro_mestre)
                db.session.commit()
            
            print("✅ Tabelas verificadas com sucesso!")
        except Exception as e:
            print(f"❌ Erro ao criar tabelas: {e}")

criar_tabelas()

# Agendador de Tarefas
def resetar_quests():
    with app.app_context():
        try:
            agora = datetime.utcnow()
            
            # Resetar quests diárias
            Quest.query.filter(
                Quest.diaria == True,
                Quest.desativada_ate <= agora
            ).update({
                'concluida': False,
                'desativada_ate': None,
                'concluida_por': None
            }, synchronize_session=False)
            
            # Resetar quests semanais (aos domingos)
            if agora.weekday() == 6:
                Quest.query.filter(
                    Quest.semanal == True,
                    Quest.desativada_ate <= agora
                ).update({
                    'concluida': False,
                    'desativada_ate': None,
                    'concluida_por': None
                }, synchronize_session=False)
            
            db.session.commit()
            print("♻️ Quests resetadas com sucesso")
        except Exception as e:
            print(f"❌ Erro ao resetar quests: {e}")
            db.session.rollback()

if not app.debug or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
    scheduler = BackgroundScheduler()
    scheduler.add_job(resetar_quests, 'interval', hours=1)
    scheduler.start()

# Funções de ajuda
def usuario_logado():
    if 'user_id' in session:
        return Usuario.query.get(session['user_id'])
    return None

def is_master():
    user = usuario_logado()
    return user and user.is_master

# Rotas de Autenticação
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        user = Usuario.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password_hash, password):
            session['user_id'] = user.id
            session['username'] = user.username
            session['is_master'] = user.is_master
            
            # Verifica se tem cavaleiro vinculado
            if user.cavaleiro:
                session['cavaleiro_id'] = user.cavaleiro.id
                session['cavaleiro_nome'] = user.cavaleiro.nome
            
            flash('Login realizado com sucesso!', 'success')
            return redirect(url_for('tabuleiro'))
        else:
            flash('Usuário ou senha incorretos', 'error')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()  # Limpa toda a sessão
    flash('Você foi deslogado', 'info')
    return redirect(url_for('login'))

@app.route('/registrar', methods=['GET', 'POST'])
def registrar():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        if Usuario.query.filter_by(username=username).first():
            flash('Username já existe', 'error')
            return redirect(url_for('registrar'))

        novo_usuario = Usuario(
            username=username,
            password_hash=generate_password_hash(password),
            is_master=False
        )
        
        db.session.add(novo_usuario)
        db.session.commit()
        flash('Registro realizado! Agora faça login', 'success')
        return redirect(url_for('login'))
    
    return render_template('registrar.html')

# Adicione esta verificação antes das rotas que exigem login
@app.before_request
def requer_login():
    rotas_permitidas = ['login', 'registrar', 'static', 'tabuleiro']
    if request.endpoint not in rotas_permitidas and 'user_id' not in session:
        return redirect(url_for('login'))

# Rotas Principais
@app.route('/')
def tabuleiro():
    try:
        conquistas = Conquista.query.order_by(Conquista.data.desc()).limit(5).all()
        cavaleiros = Cavaleiro.query.all()
        quests_globais = Quest.query.filter_by(global_quest=True).all()
        
        return render_template('tabuleiro.html',
                            cavaleiros=cavaleiros,
                            classes=CLASSES,
                            conquistas=conquistas,
                            categorias=CATEGORIAS,
                            quests_globais=quests_globais,
                            is_master=is_master(),
                            usuario_logado=usuario_logado())
    except Exception as e:
        flash('Erro ao carregar dados do banco', 'error')
        return render_template('tabuleiro.html',
                            cavaleiros=[],
                            classes=CLASSES,
                            conquistas=[],
                            categorias=CATEGORIAS,
                            quests_globais=[],
                            is_master=False,
                            usuario_logado=None)

@app.route('/cavaleiro/<int:cavaleiro_id>')
def perfil_cavaleiro(cavaleiro_id):
    try:
        cavaleiro = Cavaleiro.query.get_or_404(cavaleiro_id)
        quests = Quest.query.filter_by(cavaleiro_id=cavaleiro_id, global_quest=False).order_by(Quest.categoria).all()
        conquistas = Conquista.query.filter_by(cavaleiro_id=cavaleiro_id).order_by(Conquista.data.desc()).all()
        
        return render_template('perfil_cavaleiro.html',
                            cavaleiro=cavaleiro,
                            classes=CLASSES,
                            quests=quests,
                            conquistas=conquistas,
                            categorias=CATEGORIAS,
                            is_master=is_master(),
                            usuario_logado=usuario_logado())
    except Exception as e:
        flash('Erro ao carregar perfil', 'error')
        return redirect(url_for('tabuleiro'))

@app.route('/adicionar_cavaleiro', methods=['POST'])
def adicionar_cavaleiro():
    if not usuario_logado():
        flash('Você precisa estar logado para esta ação', 'error')
        return redirect(url_for('login'))
    
    try:
        novo_cavaleiro = Cavaleiro(
            nome=request.form['nome'],
            classe=request.form['classe'],
            usuario_id=usuario_logado().id
        )
        db.session.add(novo_cavaleiro)
        db.session.commit()
        flash('Cavaleiro adicionado com sucesso!', 'success')
    except Exception as e:
        flash(f'Erro ao adicionar cavaleiro: {str(e)}', 'error')
        db.session.rollback()
    return redirect(url_for('tabuleiro'))

@app.route('/adicionar_quest', methods=['POST'])
def adicionar_quest():
    if not usuario_logado():
        flash('Você precisa estar logado para esta ação', 'error')
        return redirect(url_for('login'))
    
    try:
        nova_quest = Quest(
            titulo=request.form['titulo'],
            descricao=request.form['descricao'],
            diaria='diaria' in request.form,
            semanal='semanal' in request.form,
            global_quest='global_quest' in request.form and is_master(),
            categoria=request.form['categoria'],
            cavaleiro_id=request.form['cavaleiro_id']
        )
        db.session.add(nova_quest)
        db.session.commit()
        flash('Quest adicionada com sucesso!', 'success')
    except Exception as e:
        flash(f'Erro ao adicionar quest: {str(e)}', 'error')
        db.session.rollback()
    
    if nova_quest.global_quest:
        return redirect(url_for('tabuleiro'))
    else:
        return redirect(url_for('perfil_cavaleiro', cavaleiro_id=request.form['cavaleiro_id']))

@app.route('/toggle_quest/<int:quest_id>')
def toggle_quest(quest_id):
    if not usuario_logado():
        flash('Você precisa estar logado para esta ação', 'error')
        return redirect(url_for('login'))
    
    try:
        quest = Quest.query.get(quest_id)
        user = usuario_logado()
        
        if not quest.concluida:
            quest.concluida = True
            quest.ultima_conclusao = datetime.utcnow()
            quest.concluida_por = user.cavaleiro.nome if user.cavaleiro else user.username
            
            if quest.diaria or quest.semanal:
                quest.desativada_ate = datetime.utcnow() + timedelta(days=1 if quest.diaria else 7)
            
            # Verificar se completou todas as quests diárias
            if not quest.global_quest and quest.diaria:
                cavaleiro = Cavaleiro.query.get(quest.cavaleiro_id)
                quests_diarias = Quest.query.filter_by(cavaleiro_id=quest.cavaleiro_id, diaria=True).all()
                
                if all(q.concluida for q in quests_diarias):
                    nova_conquista = Conquista(
                        titulo="Dia Produtivo!",
                        descricao=f"Completou todas as quests diárias em {datetime.utcnow().strftime('%d/%m/%Y')}",
                        cavaleiro_id=quest.cavaleiro_id,
                        autor_nome=user.cavaleiro.nome if user.cavaleiro else user.username
                    )
                    db.session.add(nova_conquista)
        else:
            if quest.desativada_ate is None or quest.desativada_ate <= datetime.utcnow():
                quest.concluida = False
                quest.ultima_conclusao = None
                quest.concluida_por = None
        
        db.session.commit()
        flash('Status da quest atualizado!', 'success')
    except Exception as e:
        flash(f'Erro ao atualizar quest: {str(e)}', 'error')
        db.session.rollback()
    
    if quest.global_quest:
        return redirect(url_for('tabuleiro'))
    else:
        return redirect(url_for('perfil_cavaleiro', cavaleiro_id=quest.cavaleiro_id))

@app.route('/promover_mestre/<int:usuario_id>')
def promover_mestre(usuario_id):
    if not is_master():
        flash('Apenas o Mestre da Guilda pode promover outros', 'error')
        return redirect(url_for('tabuleiro'))
    
    try:
        usuario = Usuario.query.get(usuario_id)
        usuario.is_master = True
        db.session.commit()
        flash(f'{usuario.username} foi promovido a Mestre!', 'success')
    except Exception as e:
        flash(f'Erro ao promover mestre: {str(e)}', 'error')
        db.session.rollback()
    
    return redirect(url_for('tabuleiro'))

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    with app.app_context():
        criar_tabelas()
    app.run(host='0.0.0.0', port=port)