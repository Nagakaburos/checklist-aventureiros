import os
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import inspect

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
class Cavaleiro(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(50), unique=True, nullable=False)
    classe = db.Column(db.String(20), default='Guerreiro')
    quests = db.relationship('Quest', backref='cavaleiro', lazy=True)
    conquistas = db.relationship('Conquista', backref='cavaleiro', lazy=True)

class Quest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    titulo = db.Column(db.String(200), nullable=False)
    descricao = db.Column(db.Text)
    concluida = db.Column(db.Boolean, default=False)
    diaria = db.Column(db.Boolean, default=False)
    semanal = db.Column(db.Boolean, default=False)
    categoria = db.Column(db.String(50))
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)
    ultima_conclusao = db.Column(db.DateTime)
    desativada_ate = db.Column(db.DateTime)
    cavaleiro_id = db.Column(db.Integer, db.ForeignKey('cavaleiro.id'))

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
                'desativada_ate': None
            }, synchronize_session=False)
            
            # Resetar quests semanais (aos domingos)
            if agora.weekday() == 6:
                Quest.query.filter(
                    Quest.semanal == True,
                    Quest.desativada_ate <= agora
                ).update({
                    'concluida': False,
                    'desativada_ate': None
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

# Rotas
@app.route('/')
def tabuleiro():
    try:
        conquistas = Conquista.query.order_by(Conquista.data.desc()).limit(5).all()
        cavaleiros = Cavaleiro.query.all()
        return render_template('tabuleiro.html',
                            cavaleiros=cavaleiros,
                            classes=CLASSES,
                            conquistas=conquistas,
                            categorias=CATEGORIAS)
    except Exception as e:
        flash('Erro ao carregar dados do banco', 'error')
        return render_template('tabuleiro.html',
                            cavaleiros=[],
                            classes=CLASSES,
                            conquistas=[],
                            categorias=CATEGORIAS)

@app.route('/cavaleiro/<int:cavaleiro_id>')
def perfil_cavaleiro(cavaleiro_id):
    try:
        cavaleiro = Cavaleiro.query.get_or_404(cavaleiro_id)
        quests = Quest.query.filter_by(cavaleiro_id=cavaleiro_id).order_by(Quest.categoria).all()
        conquistas = Conquista.query.filter_by(cavaleiro_id=cavaleiro_id).order_by(Conquista.data.desc()).all()
        return render_template('perfil_cavaleiro.html',
                            cavaleiro=cavaleiro,
                            classes=CLASSES,
                            quests=quests,
                            conquistas=conquistas,
                            categorias=CATEGORIAS)
    except Exception as e:
        flash('Erro ao carregar perfil', 'error')
        return redirect(url_for('tabuleiro'))

@app.route('/adicionar_cavaleiro', methods=['POST'])
def adicionar_cavaleiro():
    try:
        novo_cavaleiro = Cavaleiro(
            nome=request.form['nome'],
            classe=request.form['classe']
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
    try:
        nova_quest = Quest(
            titulo=request.form['titulo'],
            descricao=request.form['descricao'],
            diaria='diaria' in request.form,
            semanal='semanal' in request.form,
            categoria=request.form['categoria'],
            cavaleiro_id=request.form['cavaleiro_id']
        )
        db.session.add(nova_quest)
        db.session.commit()
        flash('Quest adicionada com sucesso!', 'success')
    except Exception as e:
        flash(f'Erro ao adicionar quest: {str(e)}', 'error')
        db.session.rollback()
    return redirect(url_for('perfil_cavaleiro', cavaleiro_id=request.form['cavaleiro_id']))

@app.route('/toggle_quest/<int:quest_id>')
def toggle_quest(quest_id):
    try:
        quest = Quest.query.get(quest_id)
        
        if not quest.concluida:
            quest.concluida = True
            quest.ultima_conclusao = datetime.utcnow()
            quest.desativada_ate = datetime.utcnow() + timedelta(days=1)
            
            cavaleiro = Cavaleiro.query.get(quest.cavaleiro_id)
            quests_diarias = Quest.query.filter_by(cavaleiro_id=quest.cavaleiro_id, diaria=True).all()
            if all(q.concluida for q in quests_diarias):
                nova_conquista = Conquista(
                    titulo="Dia Produtivo!",
                    descricao=f"Completou todas as quests diárias em {datetime.utcnow().strftime('%d/%m/%Y')}",
                    cavaleiro_id=quest.cavaleiro_id,
                    autor_nome=cavaleiro.nome
                )
                db.session.add(nova_conquista)
        else:
            if quest.desativada_ate is None or quest.desativada_ate <= datetime.utcnow():
                quest.concluida = False
                quest.ultima_conclusao = None
        
        db.session.commit()
        flash('Status da quest atualizado!', 'success')
    except Exception as e:
        flash(f'Erro ao atualizar quest: {str(e)}', 'error')
        db.session.rollback()
    return redirect(url_for('perfil_cavaleiro', cavaleiro_id=quest.cavaleiro_id))

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    with app.app_context():
        criar_tabelas()
    app.run(host='0.0.0.0', port=port)