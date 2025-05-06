import os
from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from flask_migrate import Migrate

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///checklist.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {"pool_pre_ping": True}
db = SQLAlchemy(app)
migrate = Migrate(app, db)

CLASSES = {
    'Guerreiro': {'icone': '⚔️', 'cor_primaria': '#8B0000', 'cor_secundaria': '#C5B358'},
    'Mago': {'icone': '🔮', 'cor_primaria': '#4B0082', 'cor_secundaria': '#ADD8E6'},
    'Arqueiro': {'icone': '🏹', 'cor_primaria': '#556B2F', 'cor_secundaria': '#F0E68C'},
    'Ladino': {'icone': '🗡️', 'cor_primaria': '#2F4F4F', 'cor_secundaria': '#708090'},
    'Clérigo': {'icone': '🙏', 'cor_primaria': '#FFD700', 'cor_secundaria': '#FFFFFF'},
    'Necromante': {'icone': '💀', 'cor_primaria': '#228B22', 'cor_secundaria': '#000000'}
}

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
    diaria = db.Column(db.Boolean, default=True)
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

def resetar_quests_diarias():
    with app.app_context():
        agora = datetime.utcnow()
        quests = Quest.query.filter(
            Quest.diaria == True,
            Quest.desativada_ate <= agora
        ).all()
        
        for quest in quests:
            quest.concluida = False
            quest.desativada_ate = None
        
        db.session.commit()

if not app.debug or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
    scheduler = BackgroundScheduler()
    scheduler.add_job(resetar_quests_diarias, 'interval', minutes=30)
    scheduler.start()

@app.route('/')
def tabuleiro():
    conquistas_recentes = Conquista.query.order_by(Conquista.data.desc()).limit(5).all()
    return render_template('tabuleiro.html', 
                         cavaleiros=Cavaleiro.query.all(),
                         classes=CLASSES,
                         conquistas=conquistas_recentes)

@app.route('/cavaleiro/<int:cavaleiro_id>')
def perfil_cavaleiro(cavaleiro_id):
    cavaleiro = Cavaleiro.query.get_or_404(cavaleiro_id)
    quests = Quest.query.filter_by(cavaleiro_id=cavaleiro_id).order_by(Quest.categoria).all()
    return render_template('perfil_cavaleiro.html',
                         cavaleiro=cavaleiro,
                         classes=CLASSES,
                         quests=quests,
                         conquistas=Conquista.query.filter_by(cavaleiro_id=cavaleiro_id).order_by(Conquista.data.desc()).all())

@app.route('/adicionar_cavaleiro', methods=['POST'])
def adicionar_cavaleiro():
    novo_cavaleiro = Cavaleiro(
        nome=request.form['nome'],
        classe=request.form['classe']
    )
    db.session.add(novo_cavaleiro)
    db.session.commit()
    return redirect(url_for('tabuleiro'))

@app.route('/adicionar_quest', methods=['POST'])
def adicionar_quest():
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
    return redirect(url_for('perfil_cavaleiro', cavaleiro_id=request.form['cavaleiro_id']))

@app.route('/adicionar_conquista', methods=['POST'])
def adicionar_conquista():
    cavaleiro = Cavaleiro.query.get(request.form['cavaleiro_id'])
    nova_conquista = Conquista(
        titulo=request.form['titulo'],
        descricao=request.form['descricao'],
        cavaleiro_id=request.form['cavaleiro_id'],
        autor_nome=cavaleiro.nome if cavaleiro else 'Aventureiro'
    )
    db.session.add(nova_conquista)
    db.session.commit()
    return redirect(url_for('perfil_cavaleiro', cavaleiro_id=request.form['cavaleiro_id']))

@app.route('/toggle_quest/<int:quest_id>')
def toggle_quest(quest_id):
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
    return redirect(url_for('perfil_cavaleiro', cavaleiro_id=quest.cavaleiro_id))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)