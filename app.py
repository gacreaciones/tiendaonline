"""
Sistema de Gestión de Inventario y E-commerce
===========================================

Aplicación Flask completa para gestión de:
- Inventario de productos
- Clientes y deudas
- Pedidos online
- Pagos parciales
- Reportes de ventas

Autor: Daniel Dominguez
Fecha: 2025-08-27
"""

# ============================================================================
# IMPORTACIONES Y CONFIGURACIÓN INICIAL
# ============================================================================

from flask import Flask, send_file, render_template, redirect, url_for, flash, request, session, abort, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user, AnonymousUserMixin
from werkzeug.security import generate_password_hash, check_password_hash
import os
from datetime import datetime, timedelta, time
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import Table, TableStyle
from io import BytesIO
import requests
from apscheduler.schedulers.background import BackgroundScheduler
import atexit
from sqlalchemy import func, extract, and_, case, text
import hashlib


# Configuración de la aplicación Flask
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'una_clave_secreta_muy_segura')

# Configuración de la base de datos usando variables de Railway
db_username = os.environ.get('MYSQLUSER', 'root')
db_password = os.environ.get('MYSQLPASSWORD', 'lVEUoeGmLirvBLKxBPProJjHLywVvreB')
db_host = os.environ.get('MYSQLHOST', 'mysql.railway.internal')
db_port = os.environ.get('MYSQLPORT', '3306')
db_name = os.environ.get('MYSQLDATABASE', 'railway')

# Construir la URI de la base de datos
app.config['SQLALCHEMY_DATABASE_URI'] = f'mysql+pymysql://{db_username}:{db_password}@{db_host}:{db_port}/{db_name}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Configuración de conexión a base de datos con pool de conexiones y SSL
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_pre_ping': True,
    'pool_recycle': 300,
    'connect_args': {
        'ssl': {
            'ssl_ca': os.environ.get('SSL_CA', None),  # Si Railway proporciona un certificado CA
        }
    }
}

db = SQLAlchemy(app)

# ============================================================================
# FORMULARIOS WTF
# ============================================================================

from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, SelectField, IntegerField, TextAreaField, BooleanField
from wtforms.validators import DataRequired, EqualTo

class EmptyForm(FlaskForm):
    """Formulario vacío para operaciones CSRF"""
    pass

class ConsultaDeudaForm(FlaskForm):
    """Formulario para consultar deudas por nombre de cliente"""
    nombre = StringField('Nombre', validators=[DataRequired()])
    submit = SubmitField('Consultar')

class LoginForm(FlaskForm):
    """Formulario de inicio de sesión"""
    username = StringField('Usuario', validators=[DataRequired()])
    password = PasswordField('Contraseña', validators=[DataRequired()])
    submit = SubmitField('Ingresar')

class ClienteForm(FlaskForm):
    """Formulario para registrar/editar clientes"""
    nombre = StringField('Nombre', validators=[DataRequired()])
    cedula = StringField('Cédula', validators=[DataRequired()])
    direccion = StringField('Dirección')
    telefono = StringField('Teléfono')
    email = StringField('Email')
    submit = SubmitField('Registrar')

class DeudaForm(FlaskForm):
    """Formulario para registrar deudas"""
    cliente_id = SelectField('Cliente', coerce=int, validators=[DataRequired()])
    guardar = SubmitField('Guardar deuda')

class ProductoDeudaForm(FlaskForm):
    """Formulario para agregar productos a una deuda"""
    producto_id = SelectField('Producto', coerce=int, validators=[DataRequired()])
    cantidad = IntegerField('Cantidad', validators=[DataRequired()])
    agregar = SubmitField('Agregar producto')

class ChangePasswordForm(FlaskForm):
    """Formulario para cambiar contraseña"""
    old_password = PasswordField('Contraseña actual', validators=[DataRequired()])
    new_password = PasswordField('Nueva contraseña', validators=[DataRequired()])
    confirm_password = PasswordField('Confirmar nueva contraseña', 
                                   validators=[DataRequired(), EqualTo('new_password', message='Las contraseñas deben coincidir')])
    submit = SubmitField('Cambiar contraseña')

class CheckoutForm(FlaskForm):
    """Formulario para finalizar compra"""
    nombre = StringField('Nombre', validators=[DataRequired()])
    direccion = StringField('Dirección', validators=[DataRequired()])
    telefono = StringField('Teléfono', validators=[DataRequired()])
    email = StringField('Email')
    notas = TextAreaField('Notas')
    submit = SubmitField('Realizar pedido')

class EmpresaForm(FlaskForm):
    """Formulario para configurar información de la empresa"""
    nombre = StringField('Nombre', validators=[DataRequired()])
    direccion = StringField('Dirección', validators=[DataRequired()])
    telefono = StringField('Teléfono', validators=[DataRequired()])
    rif = StringField('RIF', validators=[DataRequired()])
    facebook = StringField('Facebook')
    instagram = StringField('Instagram')
    twitter = StringField('Twitter')
    logo_url = StringField('Logo URL')
    submit = SubmitField('Guardar')

class ConfiguracionForm(FlaskForm):
    """Formulario para configurar apariencia del sitio"""
    hero_titulo = StringField('Título del Hero', validators=[DataRequired()])
    hero_mensaje = TextAreaField('Mensaje del Hero', validators=[DataRequired()])
    tema = SelectField('Tema', choices=[
        ('default', 'Default'),
        ('light', 'Light'),
        ('purple', 'Púrpura Elegante'),
        ('teal', 'Verde Azulado'),
        ('coral', 'Coral Vibrante'),
        ('blue', 'Azul'),
        ('green', 'Verde'),
        ('gold', 'Dorado Premium')
    ])
    submit = SubmitField('Guardar Configuración')

# ============================================================================
# MODELOS DE BASE DE DATOS
# ============================================================================

class Usuario(db.Model, UserMixin):
    """Modelo para usuarios administradores del sistema"""
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    es_admin = db.Column(db.Boolean, default=True)

class Cliente(db.Model):
    """Modelo para clientes del sistema"""
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    cedula = db.Column(db.String(20))
    rif = db.Column(db.String(20))
    direccion = db.Column(db.String(200))
    telefono = db.Column(db.String(20))
    email = db.Column(db.String(100))
    deudas = db.relationship('Deuda', backref='cliente', lazy=True)

class Producto(db.Model):
    """Modelo para productos del inventario"""
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    precio = db.Column(db.Float, nullable=False)
    cantidad = db.Column(db.Integer, default=0)
    categoria_id = db.Column(db.Integer, db.ForeignKey('categoria.id'))
    categoria = db.relationship('Categoria', backref='productos')
    imagen_url = db.Column(db.String(200))
    descripcion = db.Column(db.Text)

class Categoria(db.Model):
    """Modelo para categorías de productos"""
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(50), nullable=False, unique=True)
    descripcion = db.Column(db.String(200))
    activo = db.Column(db.Boolean, default=True)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)

class Deuda(db.Model):
    """Modelo para deudas de clientes"""
    id = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('cliente.id'), nullable=False)
    cliente_cedula = db.Column(db.String(20))
    fecha = db.Column(db.DateTime, default=datetime.utcnow)
    estado = db.Column(db.String(20), default='pendiente')  # 'pendiente' o 'pagada'
    productos = db.relationship('ProductoDeuda', backref='deuda', lazy=True)
    pagos = db.relationship('PagoParcial', backref='deuda', lazy=True)

class ProductoDeuda(db.Model):
    """Modelo para productos asociados a una deuda"""
    id = db.Column(db.Integer, primary_key=True)
    deuda_id = db.Column(db.Integer, db.ForeignKey('deuda.id'), nullable=False)
    producto_id = db.Column(db.Integer, db.ForeignKey('producto.id'), nullable=False)
    cantidad = db.Column(db.Integer, nullable=False)
    precio = db.Column(db.Float, nullable=False, default=0.0)
    producto = db.relationship('Producto', backref='deudas', lazy=True)
    nombre = db.Column(db.String(100))

class PagoParcial(db.Model):
    """Modelo para pagos parciales de deudas"""
    id = db.Column(db.Integer, primary_key=True)
    deuda_id = db.Column(db.Integer, db.ForeignKey('deuda.id'), nullable=False)
    monto_usd = db.Column(db.Float, nullable=False)
    descripcion = db.Column(db.String(200))
    fecha = db.Column(db.DateTime, default=datetime.utcnow)

class Empresa(db.Model):
    """Modelo para información de la empresa"""
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100))
    direccion = db.Column(db.String(200))
    telefono = db.Column(db.String(20))
    rif = db.Column(db.String(20))
    facebook = db.Column(db.String(200))
    instagram = db.Column(db.String(200))
    twitter = db.Column(db.String(200))
    logo_url = db.Column(db.String(200))

class Pedido(db.Model):
    """Modelo para pedidos online"""
    id = db.Column(db.Integer, primary_key=True)
    cliente_nombre = db.Column(db.String(100))
    cliente_cedula = db.Column(db.String(20))
    cliente_rif = db.Column(db.String(20))
    cliente_direccion = db.Column(db.String(200))
    cliente_telefono = db.Column(db.String(20))
    cliente_email = db.Column(db.String(100))
    notas = db.Column(db.Text)
    total = db.Column(db.Float)
    estado = db.Column(db.String(20), default='pendiente')
    fecha = db.Column(db.DateTime, default=datetime.utcnow)
    productos = db.relationship('ItemPedido', backref='pedido', lazy=True)
    
class Configuracion(db.Model):
    """Modelo para configuración del sitio web"""
    __tablename__ = 'configuracion'
    id = db.Column(db.Integer, primary_key=True)
    hero_titulo = db.Column(db.String(200), default="Bienvenido a Nuestra Tienda")
    hero_mensaje = db.Column(db.Text, default="Descubre nuestra amplia selección de productos de calidad al mejor precio. Compra fácil, rápido y seguro.")
    tema = db.Column(db.String(50), default="default")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class ItemPedido(db.Model):
    """Modelo para items individuales de un pedido"""
    id = db.Column(db.Integer, primary_key=True)
    pedido_id = db.Column(db.Integer, db.ForeignKey('pedido.id'), nullable=False)
    producto_id = db.Column(db.Integer, db.ForeignKey('producto.id'), nullable=False)
    producto_nombre = db.Column(db.String(100))
    precio = db.Column(db.Float)
    cantidad = db.Column(db.Integer)
    es_personalizado = db.Column(db.Boolean, default=False)
    medidas = db.Column(db.String(200))
    colores = db.Column(db.String(100))
    material = db.Column(db.String(100))
    descripcion_personalizada = db.Column(db.Text)

class TasaCambio(db.Model):
    """Modelo para tasas de cambio de moneda"""
    id = db.Column(db.Integer, primary_key=True)
    tasa = db.Column(db.Float, nullable=False)
    fecha_actualizacion = db.Column(db.DateTime, default=datetime.utcnow)
    fuente = db.Column(db.String(50), default='manual')
    descripcion = db.Column(db.String(200))

# ============================================================================
# FUNCIONES AUXILIARES
# ============================================================================

def es_categoria_personalizada(categoria_id):
    """Verifica si una categoría es la de productos personalizados"""
    categoria_personalizada = Categoria.query.filter_by(nombre='Personalizado').first()
    
    if not categoria_personalizada or not categoria_id:
        return False
    
    try:
        # Convertir categoria_id a int si es string
        categoria_id_int = int(categoria_id) if isinstance(categoria_id, str) else categoria_id
        return categoria_id_int == categoria_personalizada.id
    except (ValueError, TypeError):
        return False

def get_date_range(period):
    """
    Obtiene el rango de fechas para un período específico
    
    Args:
        period (str): Período solicitado ('today', 'yesterday', 'week', etc.)
    
    Returns:
        tuple: (fecha_inicio, fecha_fin)
    """
    try:
        hoy = datetime.now().date()
        
        if period == 'today':
            return hoy, hoy
        elif period == 'yesterday':
            ayer = hoy - timedelta(days=1)
            return ayer, ayer
        elif period == 'week':
            # Lunes de esta semana
            start = hoy - timedelta(days=hoy.weekday())
            return start, hoy
        elif period == 'last_week':
            # Semana pasada (lunes a domingo)
            start = hoy - timedelta(days=hoy.weekday() + 7)
            end = start + timedelta(days=6)
            return start, end
        elif period == 'month':
            # Primer día del mes actual
            start = hoy.replace(day=1)
            return start, hoy
        elif period == 'last_month':
            # Mes completo anterior
            if hoy.month == 1:
                start = hoy.replace(year=hoy.year-1, month=12, day=1)
            else:
                start = hoy.replace(month=hoy.month-1, day=1)
            end = start.replace(day=28) + timedelta(days=4)  # Último día del mes
            end = end - timedelta(days=end.day)
            return start, end
        else:
            return hoy, hoy
    except Exception as e:
        print(f"Error en get_date_range: {e}")
        hoy = datetime.now().date()
        return hoy, hoy

def calcular_ventas_periodo(fecha_inicio, fecha_fin):
    """
    Calcula las ventas totales para un período específico
    
    Args:
        fecha_inicio (date): Fecha de inicio del período
        fecha_fin (date): Fecha de fin del período
    
    Returns:
        dict: {'monto': float, 'pedidos': int}
    """
    try:
        # Convertir a datetime para incluir toda la fecha
        inicio_dt = datetime.combine(fecha_inicio, time.min)
        fin_dt = datetime.combine(fecha_fin, time.max)
        
        # Ventas de pedidos completados
        ventas_pedidos = db.session.query(
            func.sum(Pedido.total).label('total_ventas'),
            func.count(Pedido.id).label('total_transacciones')
        ).filter(
            Pedido.estado == 'completado',
            Pedido.fecha >= inicio_dt,
            Pedido.fecha <= fin_dt
        ).first()
        
        # Ventas de deudas pagadas
        deudas_pagadas = Deuda.query.filter(
            Deuda.estado == 'pagada',
            Deuda.fecha >= inicio_dt,
            Deuda.fecha <= fin_dt
        ).all()
        
        total_ventas_deudas = 0
        for deuda in deudas_pagadas:
            for producto_deuda in deuda.productos:
                producto = Producto.query.get(producto_deuda.producto_id)
                if producto:
                    total_ventas_deudas += producto.precio * producto_deuda.cantidad
        
        total_ventas = (ventas_pedidos.total_ventas or 0) + total_ventas_deudas
        total_transacciones = (ventas_pedidos.total_transacciones or 0) + len(deudas_pagadas)
        
        return {
            'monto': float(total_ventas),
            'pedidos': total_transacciones
        }
    except Exception as e:
        print(f"Error en calcular_ventas_periodo: {e}")
        import traceback
        traceback.print_exc()
        return {'monto': 0, 'pedidos': 0}

def calcular_comparacion(periodo_actual, periodo_anterior):
    """
    Calcula el cambio porcentual entre dos períodos
    
    Args:
        periodo_actual (dict): Datos del período actual
        periodo_anterior (dict): Datos del período anterior
    
    Returns:
        float: Porcentaje de cambio
    """
    try:
        if not periodo_anterior or periodo_anterior['monto'] == 0:
            if periodo_actual['monto'] == 0:
                return 0  # Ambos son 0
            return 100  # De 0 a algún valor positivo es 100% de aumento
        
        cambio = ((periodo_actual['monto'] - periodo_anterior['monto']) / periodo_anterior['monto']) * 100
        return cambio
    except Exception as e:
        print(f"Error en calcular_comparacion: {e}")
        return 0

def obtener_saldo_pendiente(deuda_id):
    """
    Calcula el saldo pendiente de una deuda específica
    
    Args:
        deuda_id (int): ID de la deuda
    
    Returns:
        float: Saldo pendiente
    """
    deuda = Deuda.query.get_or_404(deuda_id)
    
    # Calcular total de productos
    total_productos = sum(pd.precio * pd.cantidad for pd in deuda.productos)
    
    # Calcular total de pagos
    total_pagos = sum(p.monto_usd for p in deuda.pagos)
    
    return round(total_productos - total_pagos, 2)

def insert_sample_data():
    """Inserta datos de ejemplo en la base de datos"""
    if Cliente.query.first() or Producto.query.first():
        print("Datos de ejemplo ya existen, omitiendo inserción")
        return
    
    # Verificar si las categorías por defecto existen
    if not Categoria.query.first():
        categorias_default = [
            Categoria(nombre='General', descripcion='Productos generales'),
            Categoria(nombre='Alimentos', descripcion='Productos alimenticios'),
            Categoria(nombre='Bebidas', descripcion='Bebidas y refrescos'),
            Categoria(nombre='Limpieza', descripcion='Productos de limpieza'),
            Categoria(nombre='Cuidado Personal', descripcion='Productos de higiene personal')
        ]
        for categoria in categorias_default:
            db.session.add(categoria)
        db.session.commit()
        print("Categorías por defecto creadas")
    
    # Insertar algunos clientes
    cliente1 = Cliente(nombre='Juan Pérez', cedula='V12345678', direccion='Calle Principal', telefono='04141234567', email='juan@example.com')
    cliente2 = Cliente(nombre='María González', cedula='V87654321', direccion='Avenida Central', telefono='04261234567', email='maria@example.com')
    db.session.add(cliente1)
    db.session.add(cliente2)

    categoria_alimentos = Categoria.query.filter_by(nombre='Alimentos').first()
    categoria_bebidas = Categoria.query.filter_by(nombre='Bebidas').first()
    categoria_limpieza = Categoria.query.filter_by(nombre='Limpieza').first()
    
    # Insertar algunos productos con categorías válidas
    producto1 = Producto(nombre='Arroz', cantidad=100, precio=2.5, categoria_id=categoria_alimentos.id if categoria_alimentos else 1)
    producto2 = Producto(nombre='Leche', cantidad=50, precio=1.8, categoria_id=categoria_bebidas.id if categoria_bebidas else 2)
    producto3 = Producto(nombre='Jabón', cantidad=200, precio=1.2, categoria_id=categoria_limpieza.id if categoria_limpieza else 4)
    db.session.add(producto1)
    db.session.add(producto2)
    db.session.add(producto3)

    # Insertar un usuario administrador
    hashed_password = generate_password_hash('admin123', method='pbkdf2:sha256', salt_length=8)
    usuario = Usuario(username='admin', password=hashed_password, es_admin=True)
    db.session.add(usuario)

    # Insertar información de empresa
    empresa = Empresa(
        nombre='Mi Empresa',
        direccion='Av. Principal #123',
        telefono='+584121234567',
        facebook='https://facebook.com/miempresa',
        instagram='https://instagram.com/miempresa',
        logo_url='https://ejemplo.com/logo.png'
    )
    db.session.add(empresa)

    db.session.commit()

# ============================================================================
# CONFIGURACIÓN DE FLASK-LOGIN
# ============================================================================

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    """Carga un usuario por su ID para Flask-Login"""
    try:
        return Usuario.query.get(int(user_id))
    except (TypeError, ValueError):
        return None

class AnonymousUser(AnonymousUserMixin):
    """Clase para usuarios anónimos"""
    @property
    def username(self):
        return "Invitado"
    
    @property
    def es_admin(self):
        return False

login_manager.anonymous_user = AnonymousUser

# ============================================================================
# RUTAS DE INICIALIZACIÓN Y CONFIGURACIÓN
# ============================================================================

@app.route('/init_db')
def init_db():
    """
    Inicializa la base de datos con datos de ejemplo
    Crea las tablas y añade datos básicos para pruebas
    """
    with app.app_context():
        # Crear todas las tablas
        db.create_all()
        
        # Verificar si ya existen datos para evitar duplicados
        if Usuario.query.first():
            print("La base de datos ya contiene datos")
            return
        
        # Crear usuario administrador por defecto
        admin = Usuario(username='admin', password=generate_password_hash('admin123'))
        db.session.add(admin)
        
        # Crear categorías por defecto
        categorias_default = [
            Categoria(nombre='Alimentos', descripcion='Productos alimenticios'),
            Categoria(nombre='Bebidas', descripcion='Bebidas y refrescos'),
            Categoria(nombre='Limpieza', descripcion='Productos de limpieza'),
            Categoria(nombre='Cuidado Personal', descripcion='Productos de higiene personal'),
            Categoria(nombre='Hogar', descripcion='Artículos para el hogar'),
            Categoria(nombre='Personalizado', descripcion='Productos personalizados a medida')
        ]
        
        for categoria in categorias_default:
            existing = Categoria.query.filter_by(nombre=categoria.nombre).first()
            if not existing:
                db.session.add(categoria)
        
        db.session.commit()
        
        # Obtener IDs de categorías para productos
        cat_alimentos = Categoria.query.filter_by(nombre='Alimentos').first()
        cat_bebidas = Categoria.query.filter_by(nombre='Bebidas').first()
        cat_limpieza = Categoria.query.filter_by(nombre='Limpieza').first()
        cat_personalizado = Categoria.query.filter_by(nombre='Personalizado').first()
        
        productos_ejemplo = [
            # Custom product - always first
            Producto(
                nombre='Producto Personalizado - Solicita tu Cotización',
                precio=0.0,  # Price 0 for custom products
                cantidad=999999,  # Unlimited stock
                categoria_id=cat_personalizado.id if cat_personalizado else None,
                imagen_url='/placeholder.svg?height=200&width=200',
                descripcion='Diseñamos productos únicos según tus especificaciones. Comparte tus ideas y te ayudamos a crear exactamente lo que necesitas.'
            ),
            # Regular products
            Producto(nombre='Arroz', precio=2.50, cantidad=100, categoria_id=cat_alimentos.id if cat_alimentos else None),
            Producto(nombre='Frijoles', precio=3.00, cantidad=80, categoria_id=cat_alimentos.id if cat_alimentos else None),
            Producto(nombre='Aceite', precio=4.50, cantidad=50, categoria_id=cat_alimentos.id if cat_alimentos else None),
            Producto(nombre='Coca Cola', precio=1.50, cantidad=200, categoria_id=cat_bebidas.id if cat_bebidas else None),
            Producto(nombre='Agua', precio=0.75, cantidad=300, categoria_id=cat_bebidas.id if cat_bebidas else None),
            Producto(nombre='Detergente', precio=5.00, cantidad=40, categoria_id=cat_limpieza.id if cat_limpieza else None)
        ]
        
        for producto in productos_ejemplo:
            existing = Producto.query.filter_by(nombre=producto.nombre).first()
            if not existing:
                db.session.add(producto)
        
        # Crear información de empresa por defecto
        empresa = Empresa(
            nombre='Mi Tienda Online',
            direccion='Dirección de ejemplo',
            telefono='+58 123 456 7890',
            rif='J-12345678-9'
        )
        db.session.add(empresa)
        
        # Crear configuración por defecto
        config = Configuracion(
            hero_titulo='Bienvenido a Nuestra Tienda',
            hero_mensaje='Descubre nuestra amplia selección de productos de calidad al mejor precio. Compra fácil, rápido y seguro.'
        )
        db.session.add(config)
        
        db.session.commit()
        print("Base de datos inicializada con datos de ejemplo")

@app.context_processor
def inject_global_data():
    """Inyecta datos globales en todas las plantillas"""
    empresa = Empresa.query.first()
    configuracion = Configuracion.query.first()
    if not configuracion:
        configuracion = Configuracion()
        db.session.add(configuracion)
        db.session.commit()
    return dict(empresa=empresa, configuracion=configuracion)

# ============================================================================
# RUTAS PRINCIPALES Y PÚBLICAS
# ============================================================================

@app.route('/', methods=['GET', 'POST'])
def index():
    """
    Página principal del sitio web
    Muestra productos disponibles y permite consultar deudas
    """
    productos = Producto.query.options(db.joinedload(Producto.categoria)).all()
    
    categorias = Categoria.query.filter_by(activo=True).order_by(Categoria.nombre).all()
    
    return render_template('index.html', productos=productos, 
                          categorias=categorias, 
                          categoria_actual='todos',
                          form=ConsultaDeudaForm())

@app.route('/categorias/<int:categoria_id>')
def productos_por_categoria(categoria_id):
    """
    Muestra productos filtrados por categoría
    
    Args:
        categoria_id (int): ID de la categoría o 0 para 'todos'
    """
    if categoria_id == 0:
        productos = Producto.query.options(db.joinedload(Producto.categoria)).all()
        categoria_actual = 'todos'
    else:
        productos = Producto.query.options(db.joinedload(Producto.categoria)).filter(
            Producto.categoria_id == categoria_id
        ).all()
        categoria_obj = Categoria.query.get(categoria_id)
        categoria_actual = categoria_obj.nombre if categoria_obj else 'todos'
    
    categorias = Categoria.query.filter_by(activo=True).order_by(Categoria.nombre).all()
    
    return render_template('index.html', productos=productos, 
                          categorias=categorias, 
                          categoria_actual=categoria_actual,
                          form=ConsultaDeudaForm())

@app.route('/consulta_deuda_cliente', methods=['GET', 'POST'])
def consulta_deuda_cliente():
    """
    Permite a los clientes consultar sus deudas pendientes
    Ruta pública accesible sin autenticación
    """
    form = ConsultaDeudaForm()
    if form.validate_on_submit():
        nombre = form.nombre.data.strip()
        
        # Buscar cliente
        cliente = Cliente.query.filter(Cliente.nombre == nombre).first()
        if not cliente:
            flash('Cliente no encontrado', 'info')
            return redirect(url_for('index'))
        
        # Obtener todas las deudas del cliente
        deudas = Deuda.query.filter_by(cliente_id=cliente.id).all()
        
        deudas_info = []
        total_pendiente = 0.0
        
        for deuda in deudas:
            # Calcular total de la deuda
            total = 0.0
            productos_deuda = []
            for pd in deuda.productos:
                producto = Producto.query.get(pd.producto_id)
                if producto:
                    subtotal = producto.precio * pd.cantidad
                    total += subtotal
                    productos_deuda.append({
                        'producto': producto,
                        'cantidad': pd.cantidad,
                        'precio': producto.precio,
                        'subtotal': subtotal
                    })
            
            # Calcular saldo pendiente
            saldo_pendiente = total
            pagos_parciales = []
            for pago in deuda.pagos:
                saldo_pendiente -= pago.monto_usd
                pagos_parciales.append({
                    'fecha': pago.fecha,
                    'monto_usd': pago.monto_usd,
                    'descripcion': pago.descripcion
                })
            
            if deuda.estado == 'pendiente':
                total_pendiente += saldo_pendiente
            
            deudas_info.append({
                'id': deuda.id,
                'fecha': deuda.fecha,
                'estado': deuda.estado,
                'productos': productos_deuda,
                'pagos_parciales': pagos_parciales,
                'total': total,
                'saldo_pendiente': saldo_pendiente
            })
        
        # Separar deudas en pendientes y pagadas
        deudas_pendientes = [d for d in deudas_info if d['estado'] == 'pendiente']
        deudas_pagadas = [d for d in deudas_info if d['estado'] == 'pagada']
        
        return render_template('consulta_deuda_cliente.html', 
                            cliente=cliente, 
                            deudas_pendientes=deudas_pendientes,
                            deudas_pagadas=deudas_pagadas,
                            total_pendiente=total_pendiente,
                            form=EmptyForm())
    
    return redirect(url_for('index'))

# ============================================================================
# RUTAS DE AUTENTICACIÓN
# ============================================================================

@app.route('/login', methods=['GET', 'POST'])
def login():
    """
    Página de inicio de sesión para administradores
    """
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    form = LoginForm()
    if form.validate_on_submit():
        usuario = Usuario.query.filter_by(username=form.username.data).first()
        
        if usuario and check_password_hash(usuario.password, form.password.data):
            login_user(usuario)
            return redirect(url_for('dashboard'))
        
        flash('Usuario o contraseña incorrectos', 'danger')
    
    return render_template('login.html', form=form)

@app.route('/logout')
@login_required
def logout():
    """Cierra la sesión del usuario actual"""
    logout_user()
    flash('Has cerrado sesión exitosamente', 'success')
    return redirect(url_for('index'))

@app.route('/change_password', methods=['GET', 'POST'])
@login_required
def change_password():
    """
    Permite cambiar la contraseña del usuario actual
    """
    form = ChangePasswordForm()
    if form.validate_on_submit():
        try:
            if check_password_hash(current_user.password, form.old_password.data):
                hashed_password = generate_password_hash(form.new_password.data)
                current_user.password = hashed_password
                db.session.commit()
                flash('Contraseña actualizada exitosamente', 'success')
                return redirect(url_for('dashboard'))
            else:
                flash('Contraseña actual incorrecta', 'danger')
        except Exception as e:
            print(f"Error al cambiar contraseña: {e}")
            flash('Error al cambiar la contraseña', 'danger')
    
    return render_template('change_password.html', form=form)

# ============================================================================
# RUTAS DEL PANEL ADMINISTRATIVO
# ============================================================================

@app.route('/dashboard')
@login_required
def dashboard():
    """
    Panel principal de administración
    Muestra estadísticas generales del negocio
    """
    # Obtener productos
    productos = Producto.query.all()
    
    # Obtener productos con bajo stock (< 5 unidades)
    productos_bajo_stock = [p for p in productos if p.cantidad < 5]
    
    # Obtener clientes
    clientes = Cliente.query.all()
    
    # Calcular estadísticas
    total_stock = sum(p.cantidad for p in productos)
    total_value = sum(p.cantidad * p.precio for p in productos)
    
    # Obtener deudas pendientes
    deudas_pendientes = Deuda.query.filter_by(estado='pendiente').all()
    
    # Calcular total pendiente por cobrar
    total_pendiente = 0.0
    for deuda in deudas_pendientes:
        total_productos = sum(pd.cantidad * p.precio for pd in deuda.productos for p in [pd.producto])
        total_pagos = sum(p.monto_usd for p in deuda.pagos)
        total_pendiente += (total_productos - total_pagos)
    
    # Obtener pedidos pendientes
    pedidos_pendientes = Pedido.query.filter_by(estado='pendiente').order_by(Pedido.fecha.desc()).limit(5).all()
        
    # Obtener top productos más vendidos
    top_productos = db.session.query(
            Producto.nombre,
            Categoria.nombre.label('categoria_nombre'),
            func.sum(ItemPedido.cantidad).label('total_vendido')
                ).join(ItemPedido, ItemPedido.producto_id == Producto.id
                ).join(Pedido, Pedido.id == ItemPedido.pedido_id
                ).join(Categoria, Categoria.id == Producto.categoria_id
                ).filter(Pedido.estado == 'completado'
                ).group_by(Producto.id, Producto.nombre, Categoria.nombre
                ).order_by(func.sum(ItemPedido.cantidad).desc()
                ).limit(5).all()
                
    return render_template('dashboard.html',  
                            productos_bajo_stock=productos_bajo_stock,
                            clientes=clientes[:3],
                            total_stock=total_stock,
                            total_value=total_value,
                            deudas_pendientes=len(deudas_pendientes),
                            total_pendiente=total_pendiente,
                            pedidos_pendientes=pedidos_pendientes,
                            top_productos=top_productos,
                            total_orders=Pedido.query.count(),
                            total_customers=Cliente.query.count())

# ============================================================================
# RUTAS DE GESTIÓN DE CLIENTES
# ============================================================================

@app.route('/registrar_cliente', methods=['GET', 'POST'])
@login_required
def registrar_cliente():
    form = ClienteForm()
    if form.validate_on_submit():
        try:
            cliente = Cliente(
                nombre=form.nombre.data,
                cedula=form.cedula.data,
                direccion=form.direccion.data,
                telefono=form.telefono.data,
                email=form.email.data
            )
            db.session.add(cliente)
            db.session.commit()
            flash('Cliente registrado exitosamente', 'success')
            return redirect(url_for('listar_clientes'))
        except Exception as e:
            print(f"Error al registrar cliente: {e}")
            flash('Error al registrar el cliente', 'danger')
    return render_template('registrar_cliente.html', form=form)

@app.route('/clientes')
@login_required
def listar_clientes():
    """Muestra la lista de todos los clientes"""
    clientes = Cliente.query.all()
    return render_template('clientes.html', clientes=clientes, form=EmptyForm())

@app.route('/editar_cliente/<int:id>', methods=['POST'])
@login_required
def editar_cliente(id):
    """
    Edita la información de un cliente existente
    
    Args:
        id (int): ID del cliente a editar
    """
    cliente = Cliente.query.get_or_404(id)
    
    cliente.nombre = request.form.get('nombre')
    cliente.cedula = request.form.get('cedula')
    cliente.direccion = request.form.get('direccion')
    cliente.telefono = request.form.get('telefono')
    cliente.email = request.form.get('email')
    
    db.session.commit()
    flash('Cliente actualizado exitosamente', 'success')
    return redirect(url_for('listar_clientes'))

@app.route('/eliminar_cliente/<int:id>', methods=['POST'])
@login_required
def eliminar_cliente(id):
    """
    Elimina un cliente del sistema
    
    Args:
        id (int): ID del cliente a eliminar
    """
    cliente = Cliente.query.get_or_404(id)
    db.session.delete(cliente)
    db.session.commit()
    flash('Cliente eliminado correctamente', 'success')
    return redirect(url_for('listar_clientes'))

@app.route('/verificar_cliente', methods=['POST'])
def verificar_cliente():
    """
    Verifica si un cliente existe por cédula o RIF
    Usado en el proceso de checkout
    """
    try:
        identificacion = request.form.get('identificacion', '').strip().upper()
        
        if not identificacion:
            return jsonify({'success': False, 'message': 'Por favor ingrese una cédula o RIF'})
        
        # Buscar cliente por cédula o RIF
        cliente = Cliente.query.filter(
            (Cliente.cedula == identificacion) | 
            (Cliente.rif == identificacion)
        ).first()
        
        if cliente:
            return jsonify({
                'success': True, 
                'existe': True,
                'cliente': {
                    'id': cliente.id,
                    'nombre': cliente.nombre,
                    'cedula': cliente.cedula,
                    'rif': cliente.rif,
                    'direccion': cliente.direccion,
                    'telefono': cliente.telefono,
                    'email': cliente.email
                }
            })
        else:
            return jsonify({
                'success': True, 
                'existe': False,
                'identificacion': identificacion
            })
            
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error al verificar cliente: {str(e)}'})

@app.route('/gestion_deudas/<int:cliente_id>', methods=['GET'])
@login_required
def gestion_deudas(cliente_id):
    """
    Muestra todas las deudas de un cliente específico
    
    Args:
        cliente_id (int): ID del cliente
    """
    cliente = Cliente.query.get_or_404(cliente_id)
    
    # Obtener todas las deudas del cliente
    deudas = Deuda.query.filter_by(cliente_id=cliente.id).all()
    
    deudas_pendientes = []
    deudas_pagadas = []
    
    for deuda in deudas:
        # Calcular precios sin IVA (ejemplo)
        total_sin_iva = 0.0
        productos_deuda = []
        for pd in deuda.productos:
            producto = Producto.query.get(pd.producto_id)
            if producto:
                precio_sin_iva = producto.precio * 100 / 116  # Suponiendo 16% de IVA
                subtotal_sin_iva = precio_sin_iva * pd.cantidad
                total_sin_iva += subtotal_sin_iva
                
                productos_deuda.append({
                    'producto': producto,
                    'cantidad': pd.cantidad,
                    'precio_sin_iva': precio_sin_iva,
                    'subtotal_sin_iva': subtotal_sin_iva
                })
        
        # Calcular IVA y total con IVA
        iva = total_sin_iva * 0.16
        total_con_iva = total_sin_iva + iva
        
        # Calcular saldo pendiente
        saldo_pendiente = total_con_iva
        pagos_parciales = []
        for pago in deuda.pagos:
            saldo_pendiente -= pago.monto_usd
            pagos_parciales.append({
                'fecha': pago.fecha,
                'monto_usd': pago.monto_usd,
                'descripcion': pago.descripcion
            })
        
        deuda_info = {
            'id': deuda.id,
            'fecha': deuda.fecha,
            'estado': deuda.estado,
            'productos': productos_deuda,
            'pagos_parciales': pagos_parciales,
            'subtotal_sin_iva': total_sin_iva,
            'iva': iva,
            'total_con_iva': total_con_iva,
            'saldo_pendiente': saldo_pendiente
        }
        
        if deuda.estado == 'pendiente':
            deudas_pendientes.append(deuda_info)
        else:
            deudas_pagadas.append(deuda_info)
    
    return render_template('gestion_deudas.html', 
                          cliente=cliente, 
                          deudas_pendientes=deudas_pendientes,
                          deudas_pagadas=deudas_pagadas)

# ============================================================================
# RUTAS DE GESTIÓN DE PRODUCTOS
# ============================================================================

@app.route('/categorias')
@login_required
def listar_categorias():
    """Muestra la lista de todas las categorías"""
    categorias = Categoria.query.order_by(Categoria.nombre).all()
    return render_template('categorias.html', categorias=categorias, form=EmptyForm())

@app.route('/registrar_categoria', methods=['POST'])
@login_required
def registrar_categoria():
    """Registra una nueva categoría"""
    try:
        nombre = request.form.get('nombre', '').strip()
        descripcion = request.form.get('descripcion', '').strip()
        
        if not nombre:
            return jsonify({
                'success': False,
                'message': 'El nombre de la categoría es requerido'
            }), 400
        
        # Verificar si ya existe una categoría con ese nombre
        if Categoria.query.filter_by(nombre=nombre).first():
            return jsonify({
                'success': False,
                'message': 'Ya existe una categoría con ese nombre'
            }), 400
        
        categoria = Categoria(nombre=nombre, descripcion=descripcion)
        db.session.add(categoria)
        db.session.commit()
        
        return jsonify({'success': True})
    
    except Exception as e:
        print(f"Error al registrar categoría: {e}")
        return jsonify({
            'success': False,
            'message': 'Error al registrar la categoría'
        }), 500

@app.route('/editar_categoria/<int:id>', methods=['POST'])
@login_required
def editar_categoria(id):
    """Edita una categoría existente"""
    try:
        categoria = Categoria.query.get_or_404(id)
        
        nombre = request.form.get('nombre', '').strip()
        descripcion = request.form.get('descripcion', '').strip()
        activo = request.form.get('activo') == 'on'
        
        if not nombre:
            return jsonify({
                'success': False,
                'message': 'El nombre de la categoría es requerido'
            }), 400
        
        # Verificar si ya existe otra categoría con ese nombre
        existing = Categoria.query.filter(Categoria.nombre == nombre, Categoria.id != id).first()
        if existing:
            return jsonify({
                'success': False,
                'message': 'Ya existe otra categoría con ese nombre'
            }), 400
        
        categoria.nombre = nombre
        categoria.descripcion = descripcion
        categoria.activo = activo
        
        db.session.commit()
        
        return jsonify({'success': True})
    
    except Exception as e:
        print(f"Error al editar categoría: {e}")
        return jsonify({
            'success': False,
            'message': 'Error al editar la categoría'
        }), 500

@app.route('/eliminar_categoria/<int:id>', methods=['POST'])
@login_required
def eliminar_categoria(id):
    """Elimina una categoría"""
    try:
        categoria = Categoria.query.get_or_404(id)
        
        # Verificar si hay productos asociados a esta categoría
        productos_asociados = Producto.query.filter_by(categoria_id=id).count()
        if productos_asociados > 0:
            return jsonify({
                'success': False,
                'message': f'No se puede eliminar la categoría porque tiene {productos_asociados} productos asociados'
            }), 400
        
        db.session.delete(categoria)
        db.session.commit()
        
        return jsonify({'success': True})
    
    except Exception as e:
        print(f"Error al eliminar categoría: {e}")
        return jsonify({
            'success': False,
            'message': 'Error al eliminar la categoría'
        }), 500

@app.route('/api/categorias')
def api_categorias():
    """API para obtener todas las categorías activas"""
    categorias = Categoria.query.filter_by(activo=True).order_by(Categoria.nombre).all()
    return jsonify([{
        'id': c.id,
        'nombre': c.nombre,
        'descripcion': c.descripcion
    } for c in categorias])

@app.route('/registrar_producto', methods=['POST'])
@login_required
def registrar_producto():
    """Registra un nuevo producto en el inventario"""
    try:
        # Obtener datos del formulario
        nombre = request.form.get('nombre')
        cantidad = int(request.form.get('cantidad'))
        precio = float(request.form.get('precio'))
        categoria_id = request.form.get('categoria_id')
        imagen_url = request.form.get('imagen_url')
        descripcion = request.form.get('descripcion')
        
        # Validar datos básicos
        if not nombre or cantidad < 0:
            return jsonify({
                'success': False,
                'errors': {
                    'nombre': ['Nombre es requerido'] if not nombre else [],
                    'cantidad': ['Cantidad no puede ser negativa'] if cantidad < 0 else [],
                }
            }), 400
        
        # Validar precio (puede ser 0 solo para categoría Personalizado)
        if precio < 0:
            return jsonify({
                'success': False,
                'errors': {
                    'precio': ['Precio no puede ser negativo']
                }
            }), 400
        
        # Si no es categoría personalizada, el precio debe ser mayor a 0
        if not es_categoria_personalizada(categoria_id) and precio <= 0:
            return jsonify({
                'success': False,
                'errors': {
                    'precio': ['Precio debe ser mayor a cero para productos no personalizados']
                }
            }), 400
        
        # Crear y guardar producto
        producto = Producto(
            nombre=nombre,
            cantidad=cantidad,
            precio=precio,
            categoria_id=int(categoria_id) if categoria_id else None,
            imagen_url=imagen_url,
            descripcion=descripcion
        )
        db.session.add(producto)
        db.session.commit()
        
        return jsonify({'success': True})
    
    except Exception as e:
        print(f"Error al registrar producto: {e}")
        return jsonify({
            'success': False,
            'message': 'Error al registrar el producto'
        }), 500

@app.route('/productos')
@login_required
def listar_productos():
    """Muestra la lista de todos los productos"""
    productos = Producto.query.options(db.joinedload(Producto.categoria)).all()
    categorias = Categoria.query.filter_by(activo=True).order_by(Categoria.nombre).all()
    
    # Obtener la categoría Personalizado para mostrarla en el formulario
    personalizado_categoria = Categoria.query.filter_by(nombre='Personalizado').first()
    
    return render_template('productos.html', 
                         productos=productos, 
                         categorias=categorias, 
                         personalizado_categoria_id=personalizado_categoria.id if personalizado_categoria else None,
                         form=EmptyForm())

@app.route('/editar_producto/<int:id>', methods=['POST'])
@login_required
def editar_producto(id):
    """
    Edita la información de un producto existente
    
    Args:
        id (int): ID del producto a editar
    """
    try:
        producto = Producto.query.get_or_404(id)
        
        # Obtener datos del formulario
        nombre = request.form.get('nombre')
        cantidad = int(request.form.get('cantidad'))
        precio = float(request.form.get('precio'))
        categoria_id = request.form.get('categoria_id')
        imagen_url = request.form.get('imagen_url')
        descripcion = request.form.get('descripcion')
        
        # Validar datos básicos
        if not nombre or cantidad < 0:
            return jsonify({
                'success': False,
                'errors': {
                    'nombre': ['Nombre es requerido'] if not nombre else [],
                    'cantidad': ['Cantidad no puede ser negativa'] if cantidad < 0 else [],
                }
            }), 400
        
        # Validar precio (puede ser 0 solo para categoría Personalizado)
        if precio < 0:
            return jsonify({
                'success': False,
                'errors': {
                    'precio': ['Precio no puede ser negativo']
                }
            }), 400
        
        # Si no es categoría personalizada, el precio debe ser mayor a 0
        if not es_categoria_personalizada(categoria_id) and precio <= 0:
            return jsonify({
                'success': False,
                'errors': {
                    'precio': ['Precio debe ser mayor a cero para productos no personalizados']
                }
            }), 400
        
        # Actualizar producto
        producto.nombre = nombre
        producto.cantidad = cantidad
        producto.precio = precio
        producto.categoria_id = int(categoria_id) if categoria_id else None
        producto.imagen_url = imagen_url
        producto.descripcion = descripcion
        
        db.session.commit()
        
        return jsonify({'success': True})
    
    except Exception as e:
        print(f"Error al actualizar producto: {e}")
        return jsonify({
            'success': False,
            'message': 'Error al actualizar el producto'
        }), 500

@app.route('/eliminar_producto/<int:id>', methods=['POST'])
@login_required
def eliminar_producto(id):
    """
    Elimina un producto del inventario
    
    Args:
        id (int): ID del producto a eliminar
    """
    try:
        producto = Producto.query.get_or_404(id)
        db.session.delete(producto)
        db.session.commit()
        flash('Producto eliminado correctamente', 'success')
    except Exception as e:
        print(f"Error al eliminar producto: {e}")
        flash('Error al eliminar el producto', 'danger')
    return redirect(url_for('listar_productos'))

@app.route('/buscar_productos')
def buscar_productos():
    """
    API para buscar productos por nombre, categoría o descripción
    Usado para autocompletado y filtros
    """
    query = request.args.get('q', '').strip().lower()
    
    if query:
        # Búsqueda case-insensitive
        productos = Producto.query.filter(
            Producto.nombre.ilike(f'%{query}%') | 
            Producto.categoria.ilike(f'%{query}%') |
            Producto.descripcion.ilike(f'%{query}%')
        ).all()
    else:
        productos = Producto.query.all()
    
    return jsonify([{
        'id': p.id,
        'nombre': p.nombre,
        'precio': p.precio,
        'cantidad': p.cantidad,
        'categoria': p.categoria,
        'imagen_url': p.imagen_url,
        'descripcion': p.descripcion
    } for p in productos])

@app.route('/producto/<int:producto_id>')
def detalle_producto(producto_id):
    """
    API para obtener detalles de un producto específico
    
    Args:
        producto_id (int): ID del producto
    """
    producto = Producto.query.get_or_404(producto_id)
    return jsonify({
        'id': producto.id,
        'nombre': producto.nombre,
        'precio': producto.precio,
        'cantidad': producto.cantidad,
        'categoria': producto.categoria,
        'imagen_url': producto.imagen_url,
        'descripcion': producto.descripcion
    })

@app.route('/api/producto/<int:producto_id>')
def api_producto(producto_id):
    """
    API alternativa para obtener información de producto
    
    Args:
        producto_id (int): ID del producto
    """
    try:
        producto = Producto.query.get(producto_id)
        if not producto:
            return jsonify({'error': 'Producto no encontrado'}), 404
        
        return jsonify({
            'id': producto.id,
            'nombre': producto.nombre,
            'precio': producto.precio,
            'cantidad': producto.cantidad,
            'categoria': producto.categoria,
            'imagen_url': producto.imagen_url,
            'descripcion': producto.descripcion
        })
    except Exception as e:
        return jsonify({'error': 'Error interno del servidor'}), 500

# ============================================================================
# RUTAS DE GESTIÓN DE DEUDAS
# ============================================================================

@app.route('/actualizar_cantidad_temp/<int:index>', methods=['POST'])
@login_required
def actualizar_cantidad_temp(index):
    """
    Actualiza la cantidad de un producto temporalmente en la sesión
    durante el registro de una deuda
    
    Args:
        index (int): Índice del producto en la lista temporal
    """
    try:
        nueva_cantidad = int(request.form.get('cantidad'))
        
        if 'productos_deuda' in session and 0 <= index < len(session['productos_deuda']):
            # Verificar stock disponible
            producto_id = session['productos_deuda'][index]['producto_id']
            producto = Producto.query.get(producto_id)
            
            if nueva_cantidad > producto.cantidad:
                return jsonify({'success': False, 'message': f'No hay suficiente stock. Disponible: {producto.cantidad}'})
            
            session['productos_deuda'][index]['cantidad'] = nueva_cantidad
            session.modified = True
            
            return jsonify({'success': True})
        
        return jsonify({'success': False, 'message': 'Producto no encontrado'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/registrar_deuda', methods=['GET', 'POST'])
@login_required
def registrar_deuda():
    """Registra una nueva deuda en el sistema"""
    # Obtener clientes y productos
    clientes = Cliente.query.all()
    productos = Producto.query.options(db.joinedload(Producto.categoria)).all()
    
    # Crear formularios
    deuda_form = DeudaForm()
    producto_form = ProductoDeudaForm()

    # Obtener categorías únicas para el filtro
    categorias = db.session.query(Categoria.nombre).filter_by(activo=True).distinct().all()
    categorias = [cat[0] for cat in categorias]
    
    # Poblar opciones del formulario
    deuda_form.cliente_id.choices = [(c.id, f"{c.nombre} ({c.cedula})") for c in clientes]
    producto_form.producto_id.choices = [(p.id, p.nombre) for p in productos]
    
    # Inicializar lista de productos en sesión
    if 'productos_deuda' not in session:
        session['productos_deuda'] = []
    
    # Manejar agregar producto (modificado para sumar cantidades)
    if producto_form.agregar.data and producto_form.validate():
        selected_product_id = str(producto_form.producto_id.data)
        cantidad = producto_form.cantidad.data

        # Verificar stock disponible
        producto = Producto.query.get(selected_product_id)
        if cantidad > producto.cantidad:
            flash(f'No hay suficiente stock. Disponible: {producto.cantidad}', 'danger')
            return redirect(url_for('registrar_deuda'))
        
        # Verificar si el producto ya está en la lista
        producto_existente = None
        if 'productos_deuda' in session:
            for i, item in enumerate(session['productos_deuda']):
                if item['producto_id'] == selected_product_id:
                    producto_existente = i
                    break
        
        if producto_existente is not None:
            # Sumar a la cantidad existente
            nueva_cantidad = session['productos_deuda'][producto_existente]['cantidad'] + cantidad
            if nueva_cantidad > producto.cantidad:
                flash(f'No hay suficiente stock. Disponible: {producto.cantidad}', 'danger')
                return redirect(url_for('registrar_deuda'))
            
            session['productos_deuda'][producto_existente]['cantidad'] = nueva_cantidad
        else:
            # Agregar nuevo producto
            session['productos_deuda'].append({
                'producto_id': selected_product_id,
                'cantidad': cantidad
            })
        
        session.modified = True
        return redirect(url_for('registrar_deuda'))
    
    # Manejar guardar deuda
    if deuda_form.guardar.data and deuda_form.validate():
        try:
            # Obtener cliente
            cliente = Cliente.query.get(deuda_form.cliente_id.data)
            if not cliente:
                flash('Cliente no encontrado', 'danger')
                return redirect(url_for('registrar_deuda'))
            
            # Crear deuda
            deuda = Deuda(
                cliente_id=cliente.id,
                cliente_cedula=cliente.cedula,
                estado='pendiente'
            )
            db.session.add(deuda)
            db.session.flush()  # Obtener ID sin commit
            
            # Guardar productos asociados
            for item in session['productos_deuda']:
                producto = Producto.query.get(item['producto_id'])
                
                producto_deuda = ProductoDeuda(
                    deuda_id=deuda.id,
                    producto_id=producto.id,
                    cantidad=item['cantidad'],
                    precio=producto.precio  # Guardar el precio actual
                )
                db.session.add(producto_deuda)
                
                # Actualizar inventario
                producto.cantidad -= item['cantidad']
            
            db.session.commit()
            
            # Limpiar sesión
            session.pop('productos_deuda', None)
            
            flash('Deuda registrada exitosamente', 'success')
            return redirect(url_for('consultar_deudas'))
            
        except Exception as e:
            print(f"Error al registrar deuda: {e}")
            flash('Error al registrar la deuda', 'danger')
    
    # Obtener detalles de productos para mostrar
    productos_en_deuda = []
    for item in session['productos_deuda']:
        producto = Producto.query.get(item['producto_id'])
        if producto:
            subtotal = producto.precio * item['cantidad']
            
            productos_en_deuda.append({
                'id': item['producto_id'],
                'nombre': producto.nombre,
                'cantidad': item['cantidad'],
                'precio': producto.precio,
                'subtotal': subtotal
            })
        else:
            productos_en_deuda.append({
                'id': item['producto_id'],
                'nombre': 'Producto eliminado',
                'cantidad': item['cantidad'],
                'precio': 0,
                'subtotal': 0
            })
    
    # Calcular el total de la deuda
    total_deuda = sum(item['subtotal'] for item in productos_en_deuda)
    
    return render_template('registrar_deuda.html', 
                          deuda_form=deuda_form,
                          producto_form=producto_form,
                          productos_deuda=productos_en_deuda,
                          total=total_deuda,
                          clientes=clientes,  
                          productos=productos,  
                          categorias=categorias,
                          form=EmptyForm())

@app.route('/consultar_deudas')
@login_required
def consultar_deudas():
    """Muestra la lista de todas las deudas"""
    try:
        # Obtener parámetros de filtro
        estado_filtro = request.args.get('estado', 'todos')
        busqueda_filtro = request.args.get('busqueda', '').strip().lower()
        
        # Construir consulta base
        query = Deuda.query
        
        # Aplicar filtro de estado si no es 'todos'
        if estado_filtro != 'todos':
            query = query.filter(Deuda.estado == estado_filtro)
        
        # Ejecutar consulta
        deudas = query.all()
        
        # Procesar deudas para obtener información adicional
        deudas_procesadas = []
        for deuda in deudas:
            # Calcular total de la deuda - MODIFICADO: usar precio de ProductoDeuda en lugar de Producto
            total = 0.0
            for pd in deuda.productos:
                # Usar el precio almacenado en ProductoDeuda (pd.precio) en lugar del precio actual del producto
                total += pd.precio * pd.cantidad
            
            # Calcular saldo pendiente
            saldo = total
            for pago in deuda.pagos:
                saldo -= pago.monto_usd
            
            # Obtener nombre del cliente
            cliente_nombre = deuda.cliente.nombre if deuda.cliente else 'Cliente eliminado'
            
            # Aplicar filtro de búsqueda flexible
            if busqueda_filtro:
                # Buscar en cédula, nombre o ID
                busqueda_coincide = (
                    busqueda_filtro in deuda.cliente_cedula.lower() or
                    busqueda_filtro in cliente_nombre.lower() or
                    busqueda_filtro in str(deuda.id)
                )
                if not busqueda_coincide:
                    continue
                    
            deudas_procesadas.append({
                'id': deuda.id,
                'estado': deuda.estado,
                'fecha': deuda.fecha,
                'cliente_nombre': cliente_nombre,
                'cliente_cedula': deuda.cliente_cedula,
                'cliente_id': deuda.cliente_id,
                'total': total,
                'saldo_pendiente': saldo
            })
        
        # Ordenar por fecha descendente
        deudas_procesadas.sort(key=lambda x: x['fecha'], reverse=True)
        
        return render_template('consultar_deudas.html', deudas=deudas_procesadas, 
                               estado_filtro=estado_filtro, busqueda_filtro=busqueda_filtro,
                               form=EmptyForm())
    except Exception as e:
        import traceback
        traceback.print_exc()
        flash(f'Error al cargar deudas: {str(e)}', 'danger')
        return redirect(url_for('dashboard'))

@app.route('/detalle_deuda/<int:deuda_id>')
@login_required
def detalle_deuda(deuda_id):
    """
    Muestra el detalle de una deuda específica
    
    Args:
        deuda_id (int): ID de la deuda
    """
    try:
        deuda = Deuda.query.get_or_404(deuda_id)
        cliente = Cliente.query.get(deuda.cliente_id)
        empresa = Empresa.query.first()

        # Obtener productos de la deuda
        productos_deuda = []
        subtotal_sin_iva = 0.0

        # Obtener la tasa de cambio más reciente
        tasa_cambio_obj = TasaCambio.query.order_by(TasaCambio.fecha_actualizacion.desc()).first()
        tasa_actual = tasa_cambio_obj.tasa if tasa_cambio_obj else 0
        tasa_fecha = tasa_cambio_obj.fecha_actualizacion if tasa_cambio_obj else datetime.utcnow()
        
        for pd in deuda.productos:
            producto = Producto.query.get(pd.producto_id)
            if producto:
                # Usar el precio almacenado en ProductoDeuda si está disponible
                # Si no, usar el precio actual del producto
                precio = pd.precio if hasattr(pd, 'precio') else producto.precio
                precio_sin_iva = precio / 1.16  # Asumiendo 16% de IVA
                subtotal_producto = precio_sin_iva * pd.cantidad
                subtotal_sin_iva += subtotal_producto
                
                productos_deuda.append({
                    'nombre': producto.nombre,
                    'cantidad': pd.cantidad,
                    'precio_sin_iva': precio_sin_iva,
                    'subtotal': subtotal_producto
                })
        
        # Calcular totales
        iva = subtotal_sin_iva * 0.16
        total_con_iva = subtotal_sin_iva + iva
        
        # Obtener pagos realizados
        pagos_realizados = []
        total_pagado = 0.0
        for pago in deuda.pagos:
            total_pagado += pago.monto_usd
            pagos_realizados.append({
                'fecha': pago.fecha,
                'monto': pago.monto_usd,
                'descripcion': pago.descripcion or 'Pago parcial'
            })
        
        saldo_pendiente = total_con_iva - total_pagado
        
        productos_por_pagina = 6  # Máximo 6 productos por página
        total_productos = len(productos_deuda)
        
        if total_productos <= productos_por_pagina:
            return render_template('detalle_deuda.html',
                                 deuda=deuda,
                                 cliente=cliente,
                                 productos=productos_deuda,
                                 pagos=pagos_realizados,
                                 subtotal_sin_iva=subtotal_sin_iva,
                                 iva=iva,
                                 total_con_iva=total_con_iva,
                                 total_pagado=total_pagado,
                                 saldo_pendiente=saldo_pendiente,
                                 empresa=empresa,
                                 tasa_cambio=tasa_actual,
                                 tasa_cambio_obj=tasa_cambio_obj,  # Nuevo: objeto completo
                                 tasa_cambio_fecha=tasa_fecha.strftime('%d/%m/%Y %H:%M'))
        else:
            # Paginación necesaria
            total_pages = (total_productos + productos_por_pagina - 1) // productos_por_pagina
            paginated_products = []
            
            for page in range(total_pages):
                start_idx = page * productos_por_pagina
                end_idx = min(start_idx + productos_por_pagina, total_productos)
                page_products = productos_deuda[start_idx:end_idx]
                
                # Calcular subtotal de la página
                page_subtotal = sum(p['subtotal'] for p in page_products)
                
                paginated_products.append({
                    'productos': page_products,
                    'subtotal': page_subtotal
                })
            
            return render_template('detalle_deuda_paginated.html',
                                 deuda=deuda,
                                 cliente=cliente,
                                 productos=productos_deuda,
                                 paginated_products=paginated_products,
                                 total_pages=total_pages,
                                 pagos=pagos_realizados,
                                 subtotal_sin_iva=subtotal_sin_iva,
                                 iva=iva,
                                 total_con_iva=total_con_iva,
                                 total_pagado=total_pagado,
                                 saldo_pendiente=saldo_pendiente,
                                 empresa=empresa,
                                 tasa_cambio=tasa_actual,
                                 tasa_cambio_fecha=tasa_fecha.strftime('%d/%m/%Y %H:%M'))
                             
    except Exception as e:
        flash(f'Error al cargar el detalle de la deuda: {str(e)}', 'danger')
        return redirect(url_for('consultar_deudas'))


@app.route('/api/registrar_deuda_ajax', methods=['POST'])
@login_required
def registrar_deuda_ajax():
    """
    API para registrar una deuda mediante AJAX
    Recibe los datos en formato JSON
    """
    try:
        # Obtener datos como JSON
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': 'Datos no válidos'})
            
        cliente_id = data.get('cliente_id')
        productos = data.get('productos', [])
        
        if not cliente_id or not productos:
            return jsonify({'success': False, 'message': 'Datos incompletos'})
        
        # Crear deuda
        cliente = Cliente.query.get(cliente_id)
        if not cliente:
            return jsonify({'success': False, 'message': 'Cliente no encontrado'})
        
        deuda = Deuda(
            cliente_id=cliente.id,
            cliente_cedula=cliente.cedula,
            estado='pendiente'
        )
        db.session.add(deuda)
        db.session.flush()
        
        # Guardar productos asociados
        for item in productos:
            producto = Producto.query.get(item['producto_id'])
            if producto:
                # Verificar stock
                if item['cantidad'] > producto.cantidad:
                    db.session.rollback()
                    return jsonify({
                        'success': False, 
                        'message': f'No hay suficiente stock de {producto.nombre}. Disponible: {producto.cantidad}'
                    })
                
                producto_deuda = ProductoDeuda(
                    deuda_id=deuda.id,
                    producto_id=producto.id,
                    cantidad=item['cantidad'],
                    precio=producto.precio  # Guardar el precio actual
                )
                db.session.add(producto_deuda)
                
                # Actualizar inventario
                producto.cantidad -= item['cantidad']
        
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Deuda registrada exitosamente', 'deuda_id': deuda.id})
            
    except Exception as e:
        db.session.rollback()
        print(f"Error al registrar deuda: {e}")
        return jsonify({'success': False, 'message': 'Error interno al registrar la deuda'})

@app.route('/eliminar_producto_temp/<int:index>', methods=['POST'])
@login_required
def eliminar_producto_temp(index):
    """
    Elimina un producto temporalmente de la lista en sesión
    durante el registro de una deuda
    
    Args:
        index (int): Índice del producto a eliminar
    """
    if 'productos_deuda' in session and 0 <= index < len(session['productos_deuda']):
        session['productos_deuda'].pop(index)
        session.modified = True
    return redirect(url_for('registrar_deuda'))

@app.route('/marcar_pagada/<int:id>', methods=['POST'])
@login_required
def marcar_pagada(id):
    """
    Marca una deuda como pagada
    
    Args:
        id (int): ID de la deuda
    """
    deuda = Deuda.query.get_or_404(id)
    deuda.estado = 'pagada'
    db.session.commit()
    flash('Deuda marcada como pagada', 'success')
    return redirect(url_for('consultar_deudas'))

@app.route('/eliminar_deuda/<int:id>', methods=['POST'])
@login_required
def eliminar_deuda(id):
    """
    Elimina una deuda del sistema
    
    Args:
        id (int): ID de la deuda
    """
    deuda = Deuda.query.get_or_404(id)
    
    # Eliminar productos asociados y pagos
    ProductoDeuda.query.filter_by(deuda_id=id).delete()
    PagoParcial.query.filter_by(deuda_id=id).delete()
    
    # Eliminar la deuda
    db.session.delete(deuda)
    db.session.commit()
    
    flash('Deuda eliminada correctamente', 'success')
    return redirect(url_for('consultar_deudas'))

@app.route('/registrar_pago_parcial/<int:deuda_id>', methods=['POST'])
@login_required
def registrar_pago_parcial(deuda_id):
    """
    Registra un pago parcial para una deuda
    
    Args:
        deuda_id (int): ID de la deuda
    """
    try:
        deuda = Deuda.query.get_or_404(deuda_id)
        
        # Obtener datos del formulario
        monto = float(request.form.get('monto'))
        descripcion = request.form.get('descripcion', 'Pago parcial')
        metodo_pago = request.form.get('metodo_pago', 'efectivo')
        
        # Calcular saldo pendiente
        total_productos = 0
        for pd in deuda.productos:
            producto = Producto.query.get(pd.producto_id)
            if producto:
                total_productos += producto.precio * pd.cantidad
        
        total_pagos = sum(p.monto_usd for p in deuda.pagos)
        saldo_pendiente = total_productos - total_pagos
        
        # Validaciones
        if monto <= 0:
            return jsonify({'success': False, 'message': 'El monto debe ser mayor a cero'})
        
        # Ajustar automáticamente al saldo pendiente si el monto es mayor
        monto_efectivo = min(monto, saldo_pendiente)
        
        # Si hay diferencia, informar al usuario
        diferencia = monto - saldo_pendiente
        if diferencia > 0.001:  # Si pagó de más
            mensaje_ajuste = f" Se ajustó de ${monto:.2f} a ${monto_efectivo:.2f} (saldo exacto)."
        else:
            mensaje_ajuste = ""
        
        # Crear pago parcial
        pago = PagoParcial(
            deuda_id=deuda_id,
            monto_usd=monto_efectivo,
            descripcion=f"{descripcion} - {metodo_pago}"
        )
        db.session.add(pago)
        
        # Verificar si la deuda queda saldada
        nuevo_saldo = saldo_pendiente - monto_efectivo
        if abs(nuevo_saldo) <= 0.001:  # Tolerancia mínima
            deuda.estado = 'pagada'
        
        db.session.commit()
        
        mensaje = f'Pago de ${monto_efectivo:.2f} registrado exitosamente.' + mensaje_ajuste
        if deuda.estado == 'pagada':
            mensaje += ' ¡Deuda completamente pagada!'
        
        return jsonify({
            'success': True, 
            'message': mensaje,
            'nuevo_saldo': max(0, nuevo_saldo)
        })
        
    except Exception as e:
        print(f"Error al registrar pago parcial: {e}")
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Error interno al registrar el pago'})

# ============================================================================
# RUTAS DE GESTIÓN DE PEDIDOS
# ============================================================================

@app.route('/procesar_pedido/<int:pedido_id>', methods=['POST'])
@login_required
def procesar_pedido(pedido_id):
    """
    Procesa un pedido, convirtiéndolo en deuda o cancelándolo
    
    Args:
        pedido_id (int): ID del pedido
    """
    pedido = Pedido.query.get_or_404(pedido_id)
    accion = request.form.get('accion')
    
    if accion == 'aceptar':
        # Convertir pedido en deuda
        cliente = Cliente.query.filter_by(nombre=pedido.cliente_nombre).first()
        
        if not cliente:
            # Crear nuevo cliente
            cliente = Cliente(
                nombre=pedido.cliente_nombre,
                cedula='',
                direccion=pedido.cliente_direccion,
                telefono=pedido.cliente_telefono,
                email=pedido.cliente_email
            )
            db.session.add(cliente)
            db.session.flush()
        
        # Crear deuda
        deuda = Deuda(
            cliente_id=cliente.id,
            cliente_cedula=cliente.cedula,
            estado='pendiente'
        )
        db.session.add(deuda)
        db.session.flush()
        
        # Agregar productos a la deuda
        items = ItemPedido.query.filter_by(pedido_id=pedido_id).all()
        for item in items:
            producto_deuda = ProductoDeuda(
                deuda_id=deuda.id,
                producto_id=item.producto_id,
                cantidad=item.cantidad
            )
            db.session.add(producto_deuda)
        
        # Cambiar estado del pedido
        pedido.estado = 'completado'
        db.session.commit()
        
        flash('Pedido convertido en deuda exitosamente', 'success')
        return redirect(url_for('consultar_deudas'))
    
    elif accion == 'cancelar':
        # Restaurar stock
        items = ItemPedido.query.filter_by(pedido_id=pedido_id).all()
        for item in items:
            producto = Producto.query.get(item.producto_id)
            producto.cantidad += item.cantidad
        
        # Eliminar items y pedido
        ItemPedido.query.filter_by(pedido_id=pedido_id).delete()
        db.session.delete(pedido)
        db.session.commit()
        
        flash('Pedido cancelado y stock restaurado', 'success')
        return redirect(url_for('listar_pedidos'))
    
    elif accion == 'modificar':
        return redirect(url_for('editar_pedido', pedido_id=pedido_id))
    
    flash('Acción no válida', 'danger')
    return redirect(url_for('listar_pedidos'))

@app.route('/editar_pedido/<int:pedido_id>', methods=['GET', 'POST'])
@login_required
def editar_pedido(pedido_id):
    """
    Edita un pedido existente
    
    Args:
        pedido_id (int): ID del pedido
    """
    pedido = Pedido.query.get_or_404(pedido_id)
    productos = Producto.query.all()
    items = ItemPedido.query.filter_by(pedido_id=pedido_id).all()
    
    total = sum(item.precio * item.cantidad for item in items)
    
    if request.method == 'POST':
        producto_id = request.form.get('producto_id')
        cantidad = int(request.form.get('cantidad', 1))
        
        if producto_id:
            producto = Producto.query.get(producto_id)
            
            # Verificar stock
            if cantidad > producto.cantidad:
                flash(f'No hay suficiente stock. Disponible: {producto.cantidad}', 'danger')
                return redirect(url_for('editar_pedido', pedido_id=pedido_id))
            
            # Crear nuevo item
            item = ItemPedido(
                pedido_id=pedido_id,
                producto_id=producto_id,
                producto_nombre=producto.nombre,
                precio=producto.precio,
                cantidad=cantidad
            )
            db.session.add(item)
            
            # Actualizar stock
            producto.cantidad -= cantidad
            
            # Actualizar total del pedido
            pedido.total = total + (producto.precio * cantidad)
            
            db.session.commit()
            
            flash('Producto agregado al pedido', 'success')
            return redirect(url_for('editar_pedido', pedido_id=pedido_id))
    
    return render_template('editar_pedido.html', 
                          pedido=pedido, 
                          items=items, 
                          productos=productos,
                          total=total)

@app.route('/actualizar_item_pedido/<int:item_id>', methods=['POST'])
@login_required
def actualizar_item_pedido(item_id):
    """
    Actualiza la cantidad de un item de pedido
    
    Args:
        item_id (int): ID del item de pedido
    """
    item = ItemPedido.query.get_or_404(item_id)
    nueva_cantidad = int(request.form.get('cantidad'))
    diferencia = nueva_cantidad - item.cantidad
    
    # Verificar stock
    producto = Producto.query.get(item.producto_id)
    if diferencia > producto.cantidad:
        flash(f'No hay suficiente stock. Disponible: {producto.cantidad}', 'danger')
        return redirect(url_for('editar_pedido', pedido_id=item.pedido_id))
    
    # Actualizar stock
    producto.cantidad -= diferencia
    
    # Actualizar item
    item.cantidad = nueva_cantidad
    
    # Actualizar total del pedido
    pedido = Pedido.query.get(item.pedido_id)
    items = ItemPedido.query.filter_by(pedido_id=item.pedido_id).all()
    pedido.total = sum(item.precio * item.cantidad for item in items)
    
    db.session.commit()
    
    flash('Cantidad actualizada', 'success')
    return redirect(url_for('editar_pedido', pedido_id=item.pedido_id))

@app.route('/eliminar_item_pedido/<int:item_id>', methods=['POST'])
@login_required
def eliminar_item_pedido(item_id):
    """
    Elimina un item de pedido
    
    Args:
        item_id (int): ID del item de pedido
    """
    item = ItemPedido.query.get_or_404(item_id)
    pedido_id = item.pedido_id
    
    # Restaurar stock
    producto = Producto.query.get(item.producto_id)
    producto.cantidad += item.cantidad
    
    # Eliminar item
    db.session.delete(item)
    
    # Actualizar total del pedido
    pedido = Pedido.query.get(pedido_id)
    items = ItemPedido.query.filter_by(pedido_id=pedido_id).all()
    pedido.total = sum(item.precio * item.cantidad for item in items) if items else 0
    
    db.session.commit()
    
    flash('Producto eliminado del pedido', 'success')
    return redirect(url_for('editar_pedido', pedido_id=pedido_id))


@app.route('/actualizar_precio_personalizado/<int:item_id>', methods=['POST'])
@login_required
def actualizar_precio_personalizado(item_id):
    """Actualiza el precio de un producto personalizado en un pedido"""
    try:
        item = ItemPedido.query.get_or_404(item_id)
        
        if not item.es_personalizado:
            return jsonify({'success': False, 'message': 'Este producto no es personalizado'})
        
        nuevo_precio = float(request.form.get('precio', 0))
        
        if nuevo_precio <= 0:
            return jsonify({'success': False, 'message': 'El precio debe ser mayor a cero'})
        
        # Actualizar precio
        item.precio = nuevo_precio
        
        # Recalcular total del pedido
        pedido = Pedido.query.get(item.pedido_id)
        items = ItemPedido.query.filter_by(pedido_id=pedido.id).all()
        pedido.total = sum(item.precio * item.cantidad for item in items)
        
        db.session.commit()
        
        return jsonify({
            'success': True, 
            'message': 'Precio actualizado correctamente',
            'nuevo_total': pedido.total
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Error al actualizar precio: {str(e)}'})

@app.route('/eliminar_item_personalizado/<int:item_id>', methods=['POST'])
@login_required
def eliminar_item_personalizado(item_id):
    """Elimina un producto personalizado de un pedido"""
    try:
        item = ItemPedido.query.get_or_404(item_id)
        pedido_id = item.pedido_id
        
        if not item.es_personalizado:
            return jsonify({'success': False, 'message': 'Este producto no es personalizado'})
        
        # Eliminar item
        db.session.delete(item)
        
        # Actualizar total del pedido
        pedido = Pedido.query.get(pedido_id)
        items = ItemPedido.query.filter_by(pedido_id=pedido_id).all()
        pedido.total = sum(item.precio * item.cantidad for item in items) if items else 0
        
        db.session.commit()
        
        return jsonify({
            'success': True, 
            'message': 'Producto personalizado eliminado',
            'nuevo_total': pedido.total
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Error al eliminar producto: {str(e)}'})

@app.route('/cambiar_estado_pedido/<int:pedido_id>', methods=['POST'])
@login_required
def cambiar_estado_pedido(pedido_id):
    """API para cambiar el estado de un pedido mediante AJAX"""
    try:
        pedido = Pedido.query.get_or_404(pedido_id)
        data = request.get_json()
        nuevo_estado = data.get('estado')
        
        if nuevo_estado not in ['pendiente', 'procesando', 'completado', 'cancelado']:
            return jsonify({'success': False, 'message': 'Estado no válido'})
        
        # Validar que todos los productos personalizados tengan precio antes de completar
        if nuevo_estado == 'completado':
            items_personalizados = ItemPedido.query.filter_by(
                pedido_id=pedido_id, 
                es_personalizado=True
            ).all()
            
            productos_sin_precio = []
            for item in items_personalizados:
                if item.precio <= 0:
                    productos_sin_precio.append(item.producto_nombre)
            
            if productos_sin_precio:
                return jsonify({
                    'success': False, 
                    'message': f'No se puede completar el pedido. Los siguientes productos personalizados no tienen precio establecido: {", ".join(productos_sin_precio)}'
                })
        
        estado_anterior = pedido.estado
        pedido.estado = nuevo_estado
        
        # Si el pedido pasa a completado, crear deuda automáticamente
        if nuevo_estado == 'completado' and estado_anterior != 'completado':
            # Buscar o crear cliente
            cliente = Cliente.query.filter_by(nombre=pedido.cliente_nombre).first()
            
            if not cliente:
                # Crear nuevo cliente automáticamente
                cliente = Cliente(
                    nombre=pedido.cliente_nombre,
                    cedula='',  # Se puede actualizar después
                    direccion=pedido.cliente_direccion or '',
                    telefono=pedido.cliente_telefono or '',
                    email=pedido.cliente_email or ''
                )
                db.session.add(cliente)
                db.session.flush()
            
            # Crear deuda
            deuda = Deuda(
                cliente_id=cliente.id,
                cliente_cedula=cliente.cedula,
                estado='pendiente'

            )
            db.session.add(deuda)
            db.session.flush()
            
            # Agregar productos a la deuda
            items = ItemPedido.query.filter_by(pedido_id=pedido_id).all()
            for item in items:
                producto_deuda = ProductoDeuda(
                    deuda_id=deuda.id,
                    producto_id=item.producto_id,
                    cantidad=item.cantidad,
                    precio=item.precio
                )
                db.session.add(producto_deuda)
        
        # Si el pedido se cancela, restaurar stock
        elif nuevo_estado == 'cancelado':
            items = ItemPedido.query.filter_by(pedido_id=pedido_id).all()
            for item in items:
                producto = Producto.query.get(item.producto_id)
                if producto:
                    producto.cantidad += item.cantidad
        
        db.session.commit()
        return jsonify({'success': True, 'message': f'Estado cambiado a {nuevo_estado}'})
        
    except Exception as e:
        db.session.rollback()
        print(f"Error al cambiar estado: {e}")
        return jsonify({'success': False, 'message': 'Error interno del servidor'})
    
@app.route('/api/pedido/<int:pedido_id>/productos-personalizados')
@login_required
def api_productos_personalizados_pedido(pedido_id):
    """API para obtener información sobre productos personalizados en un pedido"""
    try:
        pedido = Pedido.query.get_or_404(pedido_id)
        items_personalizados = ItemPedido.query.filter_by(
            pedido_id=pedido_id, 
            es_personalizado=True
        ).all()
        
        productos_sin_precio = []
        for item in items_personalizados:
            if item.precio <= 0:
                productos_sin_precio.append(item.producto_nombre)
        
        return jsonify({
            'success': True,
            'productos_sin_precio': productos_sin_precio,
            'total_productos_personalizados': len(items_personalizados)
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/pedidos')
@login_required
def listar_pedidos():
    """Muestra la lista de todos los pedidos"""
    estado_filtro = request.args.get('estado', 'todos')
    
    if estado_filtro == 'todos':
        pedidos = Pedido.query.order_by(Pedido.fecha.desc()).all()
    else:
        pedidos = Pedido.query.filter_by(estado=estado_filtro).order_by(Pedido.fecha.desc()).all()
    return render_template('pedidos.html', pedidos=pedidos, form=EmptyForm(), estado_filtro=estado_filtro)

@app.route('/procesar_accion_pedido/<int:pedido_id>', methods=['POST'])
@login_required
def procesar_accion_pedido(pedido_id):
    """
    Procesa una acción sobre un pedido (aceptar, completar, cancelar)
    
    Args:
        pedido_id (int): ID del pedido
    """
    try:
        pedido = Pedido.query.get_or_404(pedido_id)
        accion = request.form.get('accion')
        
        if accion == 'aceptar':
            pedido.estado = 'procesando'
            db.session.commit()
            flash(f'Pedido #{pedido_id} marcado como procesando', 'info')
            
        elif accion == 'completar':
            # Buscar o crear cliente
            cliente = Cliente.query.filter_by(nombre=pedido.cliente_nombre).first()
            
            if not cliente:
                cliente = Cliente(
                    nombre=pedido.cliente_nombre,
                    cedula=pedido.cliente_cedula or '',
                    rif=pedido.cliente_rif or '',
                    direccion=pedido.cliente_direccion or '',
                    telefono=pedido.cliente_telefono or '',
                    email=pedido.cliente_email or ''
                )
                db.session.add(cliente)
                db.session.flush()
            
            # Crear deuda
            deuda = Deuda(
                cliente_id=cliente.id,
                cliente_cedula=cliente.cedula,
                estado='pendiente'
            )
            db.session.add(deuda)
            db.session.flush()
            
            # Agregar productos a la deuda
            items = ItemPedido.query.filter_by(pedido_id=pedido_id).all()
            for item in items:
                producto_deuda = ProductoDeuda(
                    deuda_id=deuda.id,
                    producto_id=item.producto_id,
                    cantidad=item.cantidad
                )
                db.session.add(producto_deuda)
            
            pedido.estado = 'completado'
            db.session.commit()
            flash(f'Pedido #{pedido_id} completado y convertido en deuda', 'success')
            
        elif accion == 'cancelar':
            # Restaurar stock
            items = ItemPedido.query.filter_by(pedido_id=pedido_id).all()
            for item in items:
                producto = Producto.query.get(item.producto_id)
                if producto:
                    producto.cantidad += item.cantidad
            
            pedido.estado = 'cancelado'
            db.session.commit()
            flash(f'Pedido #{pedido_id} cancelado y stock restaurado', 'warning')
            
        elif accion == 'pendiente':
            pedido.estado = 'pendiente'
            db.session.commit()
            flash(f'Pedido #{pedido_id} marcado como pendiente', 'info')
            
        return redirect(url_for('listar_pedidos'))
        
    except Exception as e:
        db.session.rollback()
        flash('Error al procesar la acción', 'danger')
        return redirect(url_for('listar_pedidos'))
    
@app.route('/pedido/<int:pedido_id>')
@login_required
def ver_pedido(pedido_id):
    """
    Muestra el detalle de un pedido específico
    
    Args:
        pedido_id (int): ID del pedido
    """
    pedido = Pedido.query.get_or_404(pedido_id)
    items = ItemPedido.query.filter_by(pedido_id=pedido_id).all()
    return render_template('detalle_pedido.html', pedido=pedido, items=items)

# ============================================================================
# RUTAS DE GENERACIÓN DE REPORTES
# ============================================================================

@app.route('/descargar_factura/<int:deuda_id>')
@login_required
def descargar_factura(deuda_id):
    """
    Genera y descarga la factura de una deuda en formato PDF
    
    Args:
        deuda_id (int): ID de la deuda
    """
    deuda = Deuda.query.get_or_404(deuda_id)
    cliente = Cliente.query.get(deuda.cliente_id)
    
    # Obtener productos de la deuda
    productos = []
    for pd in deuda.productos:
        producto = Producto.query.get(pd.producto_id)
        precio_sin_iva = producto.precio * 100 / 116  # Suponiendo 16% de IVA
        subtotal_sin_iva = precio_sin_iva * pd.cantidad
        productos.append({
            'nombre': producto.nombre,
            'cantidad': pd.cantidad,
            'precio_sin_iva': precio_sin_iva,
            'subtotal_sin_iva': subtotal_sin_iva
        })
    
    # Calcular totales
    subtotal = sum(p['subtotal_sin_iva'] for p in productos)
    iva = subtotal * 0.16
    total = subtotal + iva
    
    # Crear PDF
    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    
    # ... (código para generar el PDF) ...
    
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name=f"factura_{deuda_id}.pdf", mimetype='application/pdf')

# ============================================================================
# RUTAS DEL CARRITO DE COMPRAS
# ============================================================================

@app.route('/cart_count')
def cart_count():
    """
    API para obtener la cantidad de items en el carrito
    Usado para actualizar el badge en la interfaz
    """
    cart = session.get('cart', {})
    count = sum(item['quantity'] for item in cart.values())
    return jsonify({'count': count})

@app.route('/cart_sidebar_partial')
def cart_sidebar_partial():
    """
    Renderiza el partial HTML para la sidebar del carrito
    Usado para actualizar dinámicamente el contenido
    """
    cart = session.get('cart', {})
    cart_items = []
    total = 0
    for product_id, item in cart.items():
        if item.get('is_custom'):
            # Custom product - use stored data
            cart_items.append({
                'id': product_id,
                'name': item['name'],
                'price': item['price'],
                'quantity': item['quantity'],
                'subtotal': item['price'] * item['quantity'],
                'image': item['image'],
                'is_custom': True,
                'medidas': item.get('medidas', ''),
                'colores': item.get('colores', ''),
                'material': item.get('material', ''),
                'descripcion_personalizada': item.get('descripcion_personalizada', '')
            })
            total += item['price'] * item['quantity']
        else:
            # Regular product - fetch from database
            producto = Producto.query.get(product_id)
            if producto:
                item['name'] = producto.nombre
                item['price'] = float(producto.precio)
                item['image'] = producto.imagen_url
                item['subtotal'] = item['price'] * item['quantity']
                total += item['subtotal']
                cart_items.append({
                    'id': product_id,
                    'name': item['name'],
                    'price': item['price'],
                    'quantity': item['quantity'],
                    'subtotal': item['subtotal'],
                    'image': item['image']
                })
    return render_template('partials/cart_sidebar.html', cart_items=cart_items, total=total)

@app.route('/cart')
def view_cart():
    """Muestra el contenido del carrito de compras"""
    cart = session.get('cart', {})
    cart_items = []
    total = 0
    
    for product_id, item in cart.items():
        if item.get('is_custom'):
            # Custom product - use stored data
            cart_items.append({
                'id': product_id,
                'name': item['name'],
                'price': item['price'],
                'quantity': item['quantity'],
                'subtotal': item['price'] * item['quantity'],
                'image': item['image'],
                'is_custom': True,
                'medidas': item.get('medidas', ''),
                'colores': item.get('colores', ''),
                'material': item.get('material', ''),
                'descripcion_personalizada': item.get('descripcion_personalizada', '')
            })
            total += item['price'] * item['quantity']
        else:
            # Regular product - fetch from database
            producto = Producto.query.get(product_id)
            if producto:
                item['name'] = producto.nombre
                item['price'] = float(producto.precio)
                item['image'] = producto.imagen_url
                item['subtotal'] = item['price'] * item['quantity']
                total += item['subtotal']
                cart_items.append({
                    'id': product_id,
                    'name': item['name'],
                    'price': item['price'],
                    'quantity': item['quantity'],
                    'subtotal': item['subtotal'],
                    'image': item['image']
                })
    
    return render_template('cart.html', cart_items=cart_items, total=total)

@app.route('/add_to_cart/<int:product_id>', methods=['POST'])
def add_to_cart(product_id):
    """
    Añade un producto al carrito de compras
    
    Args:
        product_id (int): ID del producto
    """
    quantity = int(request.form.get('quantity', 1))
    producto = Producto.query.get_or_404(product_id)
    
    if producto.precio == 0.0 and 'Personalizado' in (producto.categoria.nombre if producto.categoria else ''):
        # This is a custom product, redirect to custom form
        return redirect(url_for('custom_product_form', product_id=product_id))
    
    # Verificar stock para productos regulares
    if quantity > producto.cantidad:
        flash(f'No hay suficiente stock. Disponible: {producto.cantidad}', 'danger')
        return redirect(url_for('index'))
    
    # Inicializar carrito
    if 'cart' not in session:
        session['cart'] = {}
    
    # Añadir o actualizar
    if str(product_id) in session['cart']:
        new_quantity = session['cart'][str(product_id)]['quantity'] + quantity
        if new_quantity > producto.cantidad:
            flash(f'No puedes agregar más de {producto.cantidad} unidades', 'danger')
            return redirect(url_for('index'))
        session['cart'][str(product_id)]['quantity'] = new_quantity
    else:
        session['cart'][str(product_id)] = {
            'quantity': quantity,
            'name': producto.nombre,
            'price': float(producto.precio),
            'image': producto.imagen_url
        }
    
    session.modified = True
    flash(f'Producto {producto.nombre} añadido al carrito', 'success')
    return redirect(url_for('index'))

@app.route('/custom_product/<int:product_id>')
def custom_product_form(product_id):
    """Shows form for custom product specifications"""
    producto = Producto.query.get_or_404(product_id)
    return render_template('custom_product_form.html', producto=producto)

@app.route('/add_custom_to_cart/<int:product_id>', methods=['POST'])
def add_custom_to_cart(product_id):
    """Adds custom product with specifications to cart"""
    producto = Producto.query.get_or_404(product_id)
    
    # Get custom specifications from form data
    medidas = request.form.get('medidas', '')
    colores = request.form.get('colores', '')
    material = request.form.get('material', '')
    descripcion_personalizada = request.form.get('descripcion_personalizada', '')
    
    # Initialize cart
    if 'cart' not in session:
        session['cart'] = {}
    
    # Create a unique identifier based on specifications
    spec_hash = hashlib.md5(f"{medidas}{colores}{material}{descripcion_personalizada}".encode()).hexdigest()
    custom_key = f"custom_{product_id}_{spec_hash}"
    
    # Check if this exact custom product already exists in cart
    if custom_key in session['cart']:
        flash('Este producto personalizado ya está en tu carrito', 'warning')
        return redirect(url_for('custom_product_form', product_id=product_id))
    
    session['cart'][custom_key] = {
        'quantity': 1,
        'name': producto.nombre,
        'price': 0.0,  # Price is 0 for custom products
        'image': producto.imagen_url,
        'is_custom': True,
        'medidas': medidas,
        'colores': colores,
        'material': material,
        'descripcion_personalizada': descripcion_personalizada,
        'original_product_id': product_id  # Store the original product ID
    }
    
    session.modified = True
    flash('Producto personalizado añadido al carrito', 'success')
    return redirect(url_for('view_cart'))

@app.route('/api/producto_detalle/<int:product_id>')
def api_producto_detalle(product_id):
    """API to get detailed product information for modal"""
    producto = Producto.query.get_or_404(product_id)
    return jsonify({
        'id': producto.id,
        'nombre': producto.nombre,
        'precio': producto.precio,
        'cantidad': producto.cantidad,
        'categoria': producto.categoria.nombre if producto.categoria else None,
        'imagen_url': producto.imagen_url,
        'descripcion': producto.descripcion,
        'es_personalizado': producto.precio == 0.0 and 'Personalizado' in (producto.categoria.nombre if producto.categoria else '')
    })

@app.route('/update_cart_quantity/<int:product_id>', methods=['POST'])
def update_cart_quantity(product_id):
    """
    Actualiza la cantidad de un producto en el carrito
    
    Args:
        product_id (int): ID del producto
    """
    new_quantity = int(request.form.get('quantity', 1))
    
    if 'cart' not in session or str(product_id) not in session['cart']:
        flash('Producto no encontrado en el carrito', 'danger')
        return redirect(url_for('view_cart'))
    
    producto = Producto.query.get(product_id)
    if new_quantity > producto.cantidad:
        flash(f'No hay suficiente stock. Disponible: {producto.cantidad}', 'danger')
        return redirect(url_for('view_cart'))
    
    session['cart'][str(product_id)]['quantity'] = new_quantity
    session.modified = True
    return redirect(url_for('view_cart'))

@app.route('/remove_from_cart/<product_id>', methods=['POST'])
def remove_from_cart(product_id):
    if 'cart' in session and product_id in session['cart']:
        del session['cart'][product_id]
        session.modified = True
        flash('Producto eliminado del carrito', 'success')
    return redirect(url_for('view_cart'))

@app.route('/verificar_identificacion', methods=['GET', 'POST'])
def verificar_identificacion():
    """
    Verifica la identificación del cliente antes del checkout
    Permite buscar un cliente existente o crear uno nuevo
    """
    if request.method == 'POST':
        identificacion = request.form.get('identificacion', '').strip().upper()
        
        if not identificacion:
            flash('Por favor ingrese su cédula o RIF', 'danger')
            return render_template('verificar_identificacion.html')
        
        # Validar formato básico (V12345678 o J123456789)
        if not (identificacion.startswith(('V', 'J', 'G', 'E', 'P')) and identificacion[1:].isdigit()):
            flash('Formato de cédula/RIF inválido. Use V12345678 o J123456789', 'danger')
            return render_template('verificar_identificacion.html')
        
        # Buscar cliente
        cliente = Cliente.query.filter(
            (Cliente.cedula == identificacion) | 
            (Cliente.rif == identificacion)
        ).first()
        
        # Guardar en sesión
        session['cliente_identificacion'] = identificacion
        
        if identificacion.startswith(('V')):
            session['cliente_cedula'] = identificacion
        else:
            session['cliente_rif'] = identificacion
        
        if cliente:
            session['cliente_checkout'] = {
                'existe': True,
                'cliente': {
                    'id': cliente.id,
                    'nombre': cliente.nombre,
                    'cedula': cliente.cedula,
                    'rif': cliente.rif,
                    'direccion': cliente.direccion,
                    'telefono': cliente.telefono,
                    'email': cliente.email
                }
            }
        else:
            session['cliente_checkout'] = {
                'existe': False,
                'identificacion': identificacion
            }
        
        return redirect(url_for('checkout'))
    
    return render_template('verificar_identificacion.html')

@app.route('/checkout', methods=['GET', 'POST'])
def checkout():
    """
    Finaliza la compra, creando un pedido y limpiando el carrito
    Requiere que el cliente haya verificado su identificación
    """
    cart = session.get('cart', {})
    if not cart:
        flash('Tu carrito está vacío', 'warning')
        return redirect(url_for('index'))
    
    # Verificar si ya tenemos la identificación del cliente
    cliente_info = session.get('cliente_checkout', None)
    
    # Si no hay información del cliente, redirigir a verificación
    if not cliente_info and request.method == 'GET':
        return redirect(url_for('verificar_identificacion'))
    
    cart_items = []
    total = 0
    
    for product_id, item in cart.items():
        if item.get('is_custom'):
            # Custom product - use stored data
            cart_items.append({
                'id': product_id,
                'name': item['name'],
                'price': item['price'],
                'quantity': item['quantity'],
                'subtotal': item['price'] * item['quantity'],
                'image': item['image'],
                'is_custom': True,
                'medidas': item.get('medidas', ''),
                'colores': item.get('colores', ''),
                'material': item.get('material', ''),
                'descripcion_personalizada': item.get('descripcion_personalizada', ''),
                'original_product_id': item.get('original_product_id')
            })
            total += item['price'] * item['quantity']
        else:
            # Regular product - fetch from database
            producto = Producto.query.get(product_id)
            if producto:
                cart_items.append({
                    'id': product_id,
                    'name': producto.nombre,
                    'price': producto.precio,
                    'quantity': item['quantity'],
                    'subtotal': producto.precio * item['quantity'],
                    'image': producto.imagen_url
                })
                total += producto.precio * item['quantity']
    
    form = CheckoutForm()
    
    cliente_id = None
    if cliente_info and cliente_info.get('existe'):
        if request.method == 'GET':
            # Solo prellenar en GET request
            form.nombre.data = cliente_info['cliente']['nombre']
            form.direccion.data = cliente_info['cliente']['direccion']
            form.telefono.data = cliente_info['cliente']['telefono']
            form.email.data = cliente_info['cliente']['email']
        # Siempre mantener el cliente_id disponible
        cliente_id = cliente_info['cliente']['id']
        session['cliente_id'] = cliente_id
    
    if form.validate_on_submit():
        try:
            cliente_id = session.get('cliente_id') or (cliente_info.get('cliente', {}).get('id') if cliente_info and cliente_info.get('existe') else None)
            
            # Si el cliente existe, actualizar sus datos ANTES de crear el pedido
            if cliente_id:
                cliente = Cliente.query.get(cliente_id)
                if cliente:
                    cliente.nombre = form.nombre.data
                    cliente.direccion = form.direccion.data
                    cliente.telefono = form.telefono.data
                    cliente.email = form.email.data
                    
                    db.session.commit()
                    flash('Tus datos de contacto han sido actualizados', 'info')
            
            # Si el cliente no existe, crearlo ANTES del pedido
            elif not cliente_info.get('existe', False):
                # Verificar si es cédula o RIF
                identificacion = session.get('cliente_identificacion', '')
                es_rif = identificacion.startswith(('J', 'G', 'E', 'P'))
                
                nuevo_cliente = Cliente(
                    nombre=form.nombre.data,
                    cedula=identificacion if not es_rif else '',
                    rif=identificacion if es_rif else '',
                    direccion=form.direccion.data,
                    telefono=form.telefono.data,
                    email=form.email.data
                )
                db.session.add(nuevo_cliente)
                db.session.flush()  # Para obtener el ID
                cliente_id = nuevo_cliente.id
            
            pedido = Pedido(
                cliente_nombre=form.nombre.data,
                cliente_direccion=form.direccion.data,
                cliente_telefono=form.telefono.data,
                cliente_email=form.email.data,
                cliente_cedula=session.get('cliente_cedula', ''),
                cliente_rif=session.get('cliente_rif', ''),
                total=total,
                notas=form.notas.data
            )
            db.session.add(pedido)
            db.session.flush()
            
            # Crear items del pedido
            for item in cart_items:
                # For custom products, use the original product ID but save custom details
                product_id = item['id']
                if item.get('is_custom'):
                    product_id = item['original_product_id']
                
                item_pedido = ItemPedido(
                    pedido_id=pedido.id,
                    producto_id=product_id,
                    producto_nombre=item['name'],
                    precio=item['price'],
                    cantidad=item['quantity'],
                    es_personalizado=item.get('is_custom', False)
                )
                
                # Add custom product details if it's a custom product
                if item.get('is_custom'):
                    item_pedido.medidas = item.get('medidas', '')
                    item_pedido.colores = item.get('colores', '')
                    item_pedido.material = item.get('material', '')
                    item_pedido.descripcion_personalizada = item.get('descripcion_personalizada', '')
                
                db.session.add(item_pedido)
                
                # Update stock only for non-custom products
                if not item.get('is_custom'):
                    producto = Producto.query.get(int(item['id']))
                    if producto:
                        producto.cantidad -= item['quantity']
            
            db.session.commit()
            
            # Limpiar sesión
            session.pop('cart', None)
            session.pop('cliente_checkout', None)
            session.pop('cliente_identificacion', None)
            session.pop('cliente_cedula', None)
            session.pop('cliente_rif', None)
            session.pop('cliente_id', None)
            
            flash('Pedido realizado con éxito. ¡Gracias!', 'success')
            return redirect(url_for('index'))
        except Exception as e:
            print(f"Error al realizar el pedido: {e}")
            flash('Error al procesar el pedido', 'danger')
            db.session.rollback()
    
    return render_template('checkout.html', form=form, total=total, cart_items=cart_items, cliente_info=cliente_info)

# ============================================================================
# RUTAS DE CONFIGURACIÓN DE LA EMPRESA
# ============================================================================

@app.route('/mi_cuenta', methods=['GET', 'POST'])
@login_required
def mi_cuenta():
    """
    Página para configurar la información de la empresa
    y la apariencia del sitio web
    """
    # Obtener o crear información de empresa
    empresa = Empresa.query.first()
    if not empresa:
        empresa = Empresa()
        db.session.add(empresa)
        db.session.commit()
    
    # Obtener o crear configuración
    configuracion = Configuracion.query.first()
    if not configuracion:
        configuracion = Configuracion()
        db.session.add(configuracion)
        db.session.commit()
    
    form = EmpresaForm()
    config_form = ConfiguracionForm()
    
    # Cargar datos existentes
    if request.method == 'GET':
        form.nombre.data = empresa.nombre
        form.direccion.data = empresa.direccion
        form.rif.data = empresa.rif
        form.telefono.data = empresa.telefono
        form.facebook.data = empresa.facebook
        form.instagram.data = empresa.instagram
        form.twitter.data = empresa.twitter
        form.logo_url.data = empresa.logo_url
        
        config_form.hero_titulo.data = configuracion.hero_titulo
        config_form.hero_mensaje.data = configuracion.hero_mensaje
        config_form.tema.data = configuracion.tema
    
    if form.validate_on_submit():
        # Actualizar información de empresa
        empresa.nombre = form.nombre.data
        empresa.direccion = form.direccion.data
        empresa.rif = form.rif.data
        empresa.telefono = form.telefono.data
        empresa.facebook = form.facebook.data
        empresa.instagram = form.instagram.data
        empresa.twitter = form.twitter.data
        empresa.logo_url = form.logo_url.data
        
        db.session.commit()
        flash('Información de la empresa actualizada correctamente', 'success')
        return redirect(url_for('mi_cuenta'))
    
    # Manejar formulario de configuración por separado
    if config_form.validate_on_submit():
        configuracion.hero_titulo = config_form.hero_titulo.data
        configuracion.hero_mensaje = config_form.hero_mensaje.data
        configuracion.tema = config_form.tema.data
        
        db.session.commit()
        flash('Configuración del sitio actualizada correctamente', 'success')
        return redirect(url_for('mi_cuenta'))
    
    return render_template('mi_cuenta.html', form=form, config_form=config_form, empresa=empresa, configuracion=configuracion)

@app.route('/actualizar_configuracion', methods=['POST'])
@login_required
def actualizar_configuracion():
    """
    API para actualizar la configuración del sitio mediante AJAX
    Recibe los datos en formato JSON
    """
    configuracion = Configuracion.query.first()
    if not configuracion:
        configuracion = Configuracion()
        db.session.add(configuracion)
    
    configuracion.hero_titulo = request.form.get('hero_titulo')
    configuracion.hero_mensaje = request.form.get('hero_mensaje')
    configuracion.tema = request.form.get('tema')
    
    db.session.commit()
    flash('Configuración del sitio actualizada correctamente', 'success')
    return redirect(url_for('mi_cuenta'))

# ============================================================================
# RUTAS DE REPORTES Y ESTADÍSTICAS
# ============================================================================

@app.route('/actualizar_tasa_manual', methods=['POST'])
@login_required
def actualizar_tasa_manual():
    """
    Actualiza la tasa de cambio manualmente mediante AJAX
    Recibe los datos en formato JSON
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': 'Datos no válidos'})
        
        nueva_tasa = data.get('tasa')
        descripcion = data.get('descripcion', 'Tasa actualizada manualmente')
        
        # Validar que la tasa sea válida
        if not nueva_tasa or nueva_tasa <= 0:
            return jsonify({'success': False, 'message': 'La tasa debe ser mayor a cero'})
        
        # Crear nueva entrada de tasa de cambio
        tasa_cambio = TasaCambio(
            tasa=float(nueva_tasa),
            fuente='manual',
            descripcion=descripcion,
            fecha_actualizacion=datetime.utcnow()
        )
        
        db.session.add(tasa_cambio)
        db.session.commit()
        
        return jsonify({
            'success': True, 
            'message': 'Tasa de cambio actualizada exitosamente',
            'tasa': float(nueva_tasa),
            'fecha': tasa_cambio.fecha_actualizacion.strftime('%d/%m/%Y %H:%M')
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Error al actualizar tasa de cambio: {e}")
        return jsonify({'success': False, 'message': 'Error interno al actualizar la tasa'})

@app.route('/api/ventas/diarias')
@login_required
def ventas_diarias():
    """
    API para obtener las ventas diarias de los últimos 7 días
    Retorna los datos en formato JSON
    """
    from sqlalchemy import func, extract, and_
    from datetime import datetime, timedelta
    
    # Últimos 7 días
    fecha_inicio = datetime.now() - timedelta(days=7)
    
    ventas = db.session.query(
        func.date(Pedido.fecha).label('fecha'),
        func.sum(Pedido.total).label('total'),
        func.count(Pedido.id).label('cantidad')
    ).filter(
        Pedido.fecha >= fecha_inicio,
        Pedido.estado == 'completado'
    ).group_by(func.date(Pedido.fecha)).all()
    
    return jsonify([{
        'fecha': v.fecha.strftime('%Y-%m-%d'),
        'total': float(v.total or 0),
        'cantidad': v.cantidad
    } for v in ventas])

@app.route('/api/ventas/semanales')
@login_required
def ventas_semanales():
    """
    API para obtener las ventas semanales de las últimas 8 semanas
    Retorna los datos en formato JSON
    """
    from sqlalchemy import func
    from datetime import datetime, timedelta
    
    # Últimas 8 semanas
    fecha_inicio = datetime.now() - timedelta(weeks=8)
    
    ventas = db.session.query(
        func.yearweek(Pedido.fecha).label('semana'),
        func.sum(Pedido.total).label('total'),
        func.count(Pedido.id).label('cantidad')
    ).filter(
        Pedido.fecha >= fecha_inicio,
        Pedido.estado == 'completado'
    ).group_by(func.yearweek(Pedido.fecha)).all()
    
    return jsonify([{
        'semana': str(v.semana),
        'total': float(v.total or 0),
        'cantidad': v.cantidad
    } for v in ventas])

@app.route('/api/ventas/mensuales')
@login_required
def ventas_mensuales():
    """
    API para obtener las ventas mensuales de los últimos 12 meses
    Retorna los datos en formato JSON
    """
    from sqlalchemy import func
    from datetime import datetime, timedelta
    
    # Últimos 12 meses
    fecha_inicio = datetime.now() - timedelta(days=365)
    
    ventas = db.session.query(
        func.year(Pedido.fecha).label('año'),
        func.month(Pedido.fecha).label('mes'),
        func.sum(Pedido.total).label('total'),
        func.count(Pedido.id).label('cantidad')
    ).filter(
        Pedido.fecha >= fecha_inicio,
        Pedido.estado == 'completado'
    ).group_by(
        func.year(Pedido.fecha),
        func.month(Pedido.fecha)
    ).all()
    
    return jsonify([{
        'año': v.año,
        'mes': v.mes,
        'total': float(v.total or 0),
        'cantidad': v.cantidad
    } for v in ventas])

@app.route('/api/ventas/resumen')
@login_required
def api_ventas_resumen():
    """
    API para obtener un resumen de ventas para un período específico
    Retorna los datos en formato JSON
    """
    try:
        periodo = request.args.get('periodo', 'month')
        print(f"Solicitando resumen para período: {periodo}")
        
        # Obtener rango de fechas para el período solicitado
        inicio, fin = get_date_range(periodo)
        print(f"Rango de fechas: {inicio} a {fin}")
        
        ventas_actual = calcular_ventas_periodo(inicio, fin)
        print(f"Ventas actuales: {ventas_actual}")
        
        # Determinar período anterior para comparación
        ventas_anterior = None
        cambio = None
        
        if periodo == 'today':
            inicio_anterior, fin_anterior = get_date_range('yesterday')
            ventas_anterior = calcular_ventas_periodo(inicio_anterior, fin_anterior)
        elif periodo == 'yesterday':
            antier = inicio - timedelta(days=1)
            ventas_anterior = calcular_ventas_periodo(antier, antier)
        elif periodo == 'week':
            inicio_anterior, fin_anterior = get_date_range('last_week')
            ventas_anterior = calcular_ventas_periodo(inicio_anterior, fin_anterior)
        elif periodo == 'last_week':
            inicio_anterior = inicio - timedelta(weeks=1)
            fin_anterior = fin - timedelta(weeks=1)
            ventas_anterior = calcular_ventas_periodo(inicio_anterior, fin_anterior)
        elif periodo == 'month':
            inicio_anterior, fin_anterior = get_date_range('last_month')
            ventas_anterior = calcular_ventas_periodo(inicio_anterior, fin_anterior)
        elif periodo == 'last_month':
            if inicio.month == 1:
                inicio_anterior = inicio.replace(year=inicio.year-1, month=12, day=1)
            else:
                inicio_anterior = inicio.replace(month=inicio.month-1, day=1)
            fin_anterior = inicio_anterior.replace(day=28) + timedelta(days=4)
            fin_anterior = fin_anterior - timedelta(days=fin_anterior.day)
            ventas_anterior = calcular_ventas_periodo(inicio_anterior, fin_anterior)
        
        print(f"Ventas anteriores: {ventas_anterior}")
        
        # Calcular cambio porcentual si hay datos del período anterior
        if ventas_anterior and ventas_anterior['monto'] is not None:
            if ventas_anterior['monto'] == 0:
                if ventas_actual['monto'] > 0:
                    cambio = 100  # De 0 a algún valor positivo
                else:
                    cambio = 0  # Ambos son 0
            else:
                cambio = ((ventas_actual['monto'] - ventas_anterior['monto']) / ventas_anterior['monto']) * 100
        
        print(f"Cambio porcentual: {cambio}")
        
        return jsonify({
            'monto': ventas_actual['monto'],
            'pedidos': ventas_actual['pedidos'],
            'cambio': cambio,
            'periodo': periodo
        })
        
    except Exception as e:
        print(f"Error en api_ventas_resumen: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/generar_pdf_pedido/<int:pedido_id>')
@login_required
def generar_pdf_pedido(pedido_id):
    """
    Genera un PDF profesional para un pedido específico
    Similar al formato de detalle_deuda pero para pedidos
    
    Args:
        pedido_id (int): ID del pedido
    """
    pedido = Pedido.query.get_or_404(pedido_id)
    
    # Obtener items del pedido con detalles completos
    items = ItemPedido.query.filter_by(pedido_id=pedido_id).all()
    productos = []
    
    for item in items:
        if item.es_personalizado:
            # Producto personalizado
            productos.append({
                'nombre': item.producto_nombre or 'Producto Personalizado',
                'cantidad': item.cantidad,
                'precio_sin_iva': item.precio * 100 / 116 if item.precio else 0,
                'subtotal': (item.precio * item.cantidad * 100 / 116) if item.precio else 0,
                'es_personalizado': True,
                'medidas': item.medidas,
                'colores': item.colores,
                'material': item.material,
                'descripcion_personalizada': item.descripcion_personalizada
            })
        else:
            # Producto regular
            precio_sin_iva = item.precio * 100 / 116 if item.precio else 0
            subtotal_sin_iva = precio_sin_iva * item.cantidad
            productos.append({
                'nombre': item.producto_nombre,
                'cantidad': item.cantidad,
                'precio_sin_iva': precio_sin_iva,
                'subtotal': subtotal_sin_iva,
                'es_personalizado': False
            })
    
    # Calcular totales
    subtotal_sin_iva = sum(p['subtotal'] for p in productos)
    iva = subtotal_sin_iva * 0.16
    total_con_iva = subtotal_sin_iva + iva
    
    # Obtener información de empresa y tasa de cambio
    empresa = Empresa.query.first()
    tasa_cambio_obj = TasaCambio.query.order_by(TasaCambio.fecha_actualizacion.desc()).first()
    tasa_cambio = tasa_cambio_obj.tasa if tasa_cambio_obj else 50.0
    tasa_cambio_fecha = tasa_cambio_obj.fecha_actualizacion.strftime('%d/%m/%Y') if tasa_cambio_obj else 'No disponible'
    
    # Crear cliente ficticio para el template (ya que los pedidos no tienen cliente asociado)
    cliente = {
        'nombre': pedido.cliente_nombre,
        'cedula': pedido.cliente_cedula or pedido.cliente_rif or 'Sin identificación',
        'direccion': pedido.cliente_direccion,
        'telefono': pedido.cliente_telefono
    }
    
    return render_template('detalle_pedido_pdf.html',
                          pedido=pedido,
                          cliente=cliente,
                          productos=productos,
                          subtotal_sin_iva=subtotal_sin_iva,
                          iva=iva,
                          total_con_iva=total_con_iva,
                          empresa=empresa,
                          tasa_cambio=tasa_cambio,
                          tasa_cambio_fecha=tasa_cambio_fecha,
                          tasa_cambio_obj=tasa_cambio_obj)

# ============================================================================
# INICIO DE LA APLICACIÓN
# ============================================================================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
