from flask import Flask, send_file, render_template, redirect, url_for, flash, request, session, abort, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user, AnonymousUserMixin
from werkzeug.security import generate_password_hash, check_password_hash
import os
from datetime import datetime
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import Table, TableStyle
from io import BytesIO


app = Flask(__name__)
app.config['SECRET_KEY'] = 'una_clave_secreta_muy_segura'
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://flask_admin:daniel!123456@192.168.51.21/decomilca'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Formularios
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired

class EmptyForm(FlaskForm):
    pass

class ConsultaDeudaForm(FlaskForm):
    nombre = StringField('Nombre', validators=[DataRequired()])
    submit = SubmitField('Consultar')

class LoginForm(FlaskForm):
    username = StringField('Usuario', validators=[DataRequired()])
    password = PasswordField('Contraseña', validators=[DataRequired()])
    submit = SubmitField('Ingresar')

class ClienteForm(FlaskForm):
    nombre = StringField('Nombre', validators=[DataRequired()])
    cedula = StringField('Cédula', validators=[DataRequired()])
    direccion = StringField('Dirección')
    telefono = StringField('Teléfono')
    email = StringField('Email')
    submit = SubmitField('Registrar')

# Formulario para registrar deuda
from wtforms import SelectField, IntegerField, FieldList, FormField, BooleanField
class DeudaForm(FlaskForm):
    cliente_id = SelectField('Cliente', coerce=int, validators=[DataRequired()])
    guardar = SubmitField('Guardar deuda')

# Formulario para agregar productos a la deuda
class ProductoDeudaForm(FlaskForm):
    producto_id = SelectField('Producto', coerce=int, validators=[DataRequired()])
    cantidad = IntegerField('Cantidad', validators=[DataRequired()])
    agregar = SubmitField('Agregar producto')

# Definición de modelos


class Usuario(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)
    es_admin = db.Column(db.Boolean, default=True)

class Cliente(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    cedula = db.Column(db.String(20), nullable=False)
    direccion = db.Column(db.String(200))
    telefono = db.Column(db.String(20))
    email = db.Column(db.String(100))
    deudas = db.relationship('Deuda', backref='cliente', lazy=True)

class Producto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    cantidad = db.Column(db.Integer, nullable=False)
    precio = db.Column(db.Float, nullable=False)
    categoria = db.Column(db.String(50))
    imagen_url = db.Column(db.String(200))
    fecha = db.Column(db.DateTime, default=datetime.utcnow)

class Deuda(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('cliente.id'), nullable=False)
    cliente_cedula = db.Column(db.String(20))
    fecha = db.Column(db.DateTime, default=datetime.utcnow)
    estado = db.Column(db.String(20), default='pendiente')  # 'pendiente' o 'pagada'
    productos = db.relationship('ProductoDeuda', backref='deuda', lazy=True)
    pagos = db.relationship('PagoParcial', backref='deuda', lazy=True)

class ProductoDeuda(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    deuda_id = db.Column(db.Integer, db.ForeignKey('deuda.id'), nullable=False)
    producto_id = db.Column(db.Integer, db.ForeignKey('producto.id'), nullable=False)
    cantidad = db.Column(db.Integer, nullable=False)

class PagoParcial(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    deuda_id = db.Column(db.Integer, db.ForeignKey('deuda.id'), nullable=False)
    monto_usd = db.Column(db.Float, nullable=False)
    descripcion = db.Column(db.String(200))
    fecha = db.Column(db.DateTime, default=datetime.utcnow)

class Empresa(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100))
    direccion = db.Column(db.String(200))
    telefono = db.Column(db.String(20))
    facebook = db.Column(db.String(200))
    instagram = db.Column(db.String(200))
    twitter = db.Column(db.String(200))
    logo_url = db.Column(db.String(200))

class Pedido(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cliente_nombre = db.Column(db.String(100))
    cliente_direccion = db.Column(db.String(200))
    cliente_telefono = db.Column(db.String(20))
    cliente_email = db.Column(db.String(100))
    total = db.Column(db.Float)
    estado = db.Column(db.String(20), default='pendiente')
    fecha = db.Column(db.DateTime, default=datetime.utcnow)

class ItemPedido(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    pedido_id = db.Column(db.Integer, db.ForeignKey('pedido.id'), nullable=False)
    producto_id = db.Column(db.Integer, db.ForeignKey('producto.id'), nullable=False)
    producto_nombre = db.Column(db.String(100))
    precio = db.Column(db.Float)
    cantidad = db.Column(db.Integer)

# Configuración de Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    try:
        return Usuario.query.get(int(user_id))
    except (TypeError, ValueError):
        return None  # Devuelve None si no es un entero válido

# Clase para usuarios anónimos
class AnonymousUser(AnonymousUserMixin):
    @property
    def username(self):
        return "Invitado"
    
    @property
    def es_admin(self):
        return False

login_manager.anonymous_user = AnonymousUser

# Ruta para inicializar la base de datos
@app.route('/init_db')
def init_db():
    db.create_all()
    insert_sample_data()
    return 'Base de datos inicializada con datos de ejemplo!'

def insert_sample_data():
    # Insertar algunos clientes
    cliente1 = Cliente(nombre='Juan Pérez', cedula='V12345678', direccion='Calle Principal', telefono='04141234567', email='juan@example.com')
    cliente2 = Cliente(nombre='María González', cedula='V87654321', direccion='Avenida Central', telefono='04261234567', email='maria@example.com')
    db.session.add(cliente1)
    db.session.add(cliente2)

    # Insertar algunos productos
    producto1 = Producto(nombre='Arroz', cantidad=100, precio=2.5, categoria='Alimentos')
    producto2 = Producto(nombre='Leche', cantidad=50, precio=1.8, categoria='Lácteos')
    producto3 = Producto(nombre='Jabón', cantidad=200, precio=1.2, categoria='Limpieza')
    db.session.add(producto1)
    db.session.add(producto2)
    db.session.add(producto3)

    # Insertar un usuario
    hashed_password = generate_password_hash(
    'admin123', 
    method='pbkdf2:sha256', 
    salt_length=8  # Reduce la longitud del salt
    )
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

# Ruta principal
@app.route('/', methods=['GET', 'POST'])
def index():
    # Obtener productos con stock
    productos = Producto.query.filter(Producto.cantidad > 0).all()
    
    # Obtener todas las categorías únicas
    categorias = db.session.query(Producto.categoria).distinct().all()
    categorias = [cat[0] for cat in categorias if cat[0] is not None]
    
    return render_template('index.html', productos=productos, 
                          categorias=sorted(categorias), 
                          categoria_actual='todos',
                          form=ConsultaDeudaForm())

# Ruta de login
@app.route('/login', methods=['GET', 'POST'])
def login():
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
    logout_user()
    flash('Has cerrado sesión exitosamente', 'success')
    return redirect(url_for('index'))

# Ruta de dashboard
@app.route('/dashboard')
@login_required
def dashboard():
    # Obtener productos
    productos = Producto.query.all()
    
    # Obtener productos con bajo stock (<5 unidades)
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
    
    # Obtener top 5 deudores con deudas más antiguas
    top_deudores = Deuda.query.filter_by(estado='pendiente').order_by(Deuda.fecha).limit(5).all()
    
    return render_template('dashboard.html',  
                           productos_bajo_stock=productos_bajo_stock,
                           clientes=clientes[:3],
                           total_stock=total_stock,
                           total_value=total_value,
                           deudas_pendientes=len(deudas_pendientes),
                           top_deudores=top_deudores,
                           total_pendiente=total_pendiente,
                           form=EmptyForm())

# Ruta para registrar cliente
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

# Ruta para listar clientes
@app.route('/clientes')
@login_required
def listar_clientes():
    clientes = Cliente.query.all()
    return render_template('clientes.html', clientes=clientes, form=EmptyForm())

# Ruta para editar cliente
@app.route('/editar_cliente/<int:id>', methods=['POST'])
@login_required
def editar_cliente(id):
    cliente = Cliente.query.get_or_404(id)
    
    cliente.nombre = request.form.get('nombre')
    cliente.cedula = request.form.get('cedula')
    cliente.direccion = request.form.get('direccion')
    cliente.telefono = request.form.get('telefono')
    cliente.email = request.form.get('email')
    
    db.session.commit()
    flash('Cliente actualizado exitosamente', 'success')
    return redirect(url_for('listar_clientes'))

# Ruta para eliminar cliente
@app.route('/eliminar_cliente/<int:id>', methods=['POST'])
@login_required
def eliminar_cliente(id):
    cliente = Cliente.query.get_or_404(id)
    db.session.delete(cliente)
    db.session.commit()
    flash('Cliente eliminado correctamente', 'success')
    return redirect(url_for('listar_clientes'))

# Add after the cart routes
@app.route('/cart_count')
def cart_count():
    cart = session.get('cart', {})
    count = sum(item['quantity'] for item in cart.values())
    return jsonify({'count': count})

@app.route('/cart_sidebar_partial')
def cart_sidebar_partial():
    cart = session.get('cart', {})
    cart_items = []
    total = 0
    for product_id, item in cart.items():
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

# Ruta para registrar producto
@app.route('/registrar_producto', methods=['POST'])
@login_required
def registrar_producto():
    try:
        # Obtener datos del formulario
        nombre = request.form.get('nombre')
        cantidad = int(request.form.get('cantidad'))
        precio = float(request.form.get('precio'))
        categoria = request.form.get('categoria')
        imagen_url = request.form.get('imagen_url')
        
        # Validar datos básicos
        if not nombre or cantidad < 0 or precio <= 0:
            return jsonify({
                'success': False,
                'errors': {
                    'nombre': ['Nombre es requerido'] if not nombre else [],
                    'cantidad': ['Cantidad no puede ser negativa'] if cantidad < 0 else [],
                    'precio': ['Precio debe ser mayor a cero'] if precio <= 0 else []
                }
            }), 400
        
        # Crear y guardar producto
        producto = Producto(
            nombre=nombre,
            cantidad=cantidad,
            precio=precio,
            categoria=categoria,
            imagen_url=imagen_url
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

# Ruta para listar productos
@app.route('/productos')
@login_required
def listar_productos():
    productos = Producto.query.all()
    return render_template('productos.html', productos=productos, form=EmptyForm())

# Ruta para editar producto
@app.route('/editar_producto/<int:id>', methods=['POST'])
@login_required
def editar_producto(id):
    try:
        producto = Producto.query.get_or_404(id)
        
        # Obtener datos del formulario
        nombre = request.form.get('nombre')
        cantidad = int(request.form.get('cantidad'))
        precio = float(request.form.get('precio'))
        categoria = request.form.get('categoria')
        imagen_url = request.form.get('imagen_url')
        
        # Validar datos básicos
        if not nombre or cantidad < 0 or precio <= 0:
            return jsonify({
                'success': False,
                'errors': {
                    'nombre': ['Nombre es requerido'] if not nombre else [],
                    'cantidad': ['Cantidad no puede ser negativa'] if cantidad < 0 else [],
                    'precio': ['Precio debe ser mayor a cero'] if precio <= 0 else []
                }
            }), 400
        
        # Actualizar producto
        producto.nombre = nombre
        producto.cantidad = cantidad
        producto.precio = precio
        producto.categoria = categoria
        producto.imagen_url = imagen_url
        
        db.session.commit()
        
        return jsonify({'success': True})
    
    except Exception as e:
        print(f"Error al actualizar producto: {e}")
        return jsonify({
            'success': False,
            'message': 'Error al actualizar el producto'
        }), 500

# Ruta para eliminar producto
@app.route('/eliminar_producto/<int:id>', methods=['POST'])
@login_required
def eliminar_producto(id):
    try:
        producto = Producto.query.get_or_404(id)
        db.session.delete(producto)
        db.session.commit()
        flash('Producto eliminado correctamente', 'success')
    except Exception as e:
        print(f"Error al eliminar producto: {e}")
        flash('Error al eliminar el producto', 'danger')
    return redirect(url_for('listar_productos'))

# Ruta para registrar deuda
@app.route('/registrar_deuda', methods=['GET', 'POST'])
@login_required
def registrar_deuda():
    # Obtener clientes y productos
    clientes = Cliente.query.all()
    productos = Producto.query.all()
    
    # Crear formularios
    deuda_form = DeudaForm()
    producto_form = ProductoDeudaForm()
    
    # Poblar opciones del formulario
    deuda_form.cliente_id.choices = [(c.id, f"{c.nombre} ({c.cedula})") for c in clientes]
    producto_form.producto_id.choices = [(p.id, p.nombre) for p in productos]
    
    # Inicializar lista de productos en sesión
    if 'productos_deuda' not in session:
        session['productos_deuda'] = []
    
    # Manejar agregar producto
    if producto_form.agregar.data and producto_form.validate():
        selected_product_id = str(producto_form.producto_id.data)
        cantidad = producto_form.cantidad.data

        # Verificar stock disponible
        producto = Producto.query.get(selected_product_id)
        if cantidad > producto.cantidad:
            flash(f'No hay suficiente stock. Disponible: {producto.cantidad}', 'danger')
            return redirect(url_for('registrar_deuda'))
        
        # Agregar producto si hay stock suficiente
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
                
                # Crear relación producto-deuda
                producto_deuda = ProductoDeuda(
                    deuda_id=deuda.id,
                    producto_id=producto.id,
                    cantidad=item['cantidad']
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
                          form=EmptyForm())

# Ruta para consultar deudas
@app.route('/consultar_deudas')
@login_required
def consultar_deudas():
    try:
        # Obtener parámetros de filtro
        estado_filtro = request.args.get('estado', 'todos')
        cedula_filtro = request.args.get('cedula', '').strip().lower()
        
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
            # Calcular total de la deuda
            total = 0.0
            for pd in deuda.productos:
                producto = Producto.query.get(pd.producto_id)
                if producto:
                    total += producto.precio * pd.cantidad
            
            # Calcular saldo pendiente
            saldo = total
            for pago in deuda.pagos:
                saldo -= pago.monto_usd
            
            # Obtener nombre del cliente
            cliente_nombre = deuda.cliente.nombre if deuda.cliente else 'Cliente eliminado'
            
            # Aplicar filtro de cédula
            if cedula_filtro and cedula_filtro not in deuda.cliente_cedula.lower():
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
                               estado_filtro=estado_filtro, cedula_filtro=cedula_filtro,
                               form=EmptyForm())
    except Exception as e:
        import traceback
        traceback.print_exc()
        flash(f'Error al cargar deudas: {str(e)}', 'danger')
        return redirect(url_for('dashboard'))

# Resto de rutas (similares a las anteriores pero adaptadas a SQLAlchemy)
# ...

# Ruta para consultar deuda de cliente
@app.route('/consulta_deuda_cliente', methods=['GET', 'POST'])
def consulta_deuda_cliente():
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

# Ruta para gestionar deudas de un cliente
@app.route('/gestion_deudas/<int:cliente_id>', methods=['GET'])
@login_required
def gestion_deudas(cliente_id):
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

# Ruta para registrar pago parcial
@app.route('/registrar_pago_parcial/<int:deuda_id>', methods=['POST'])
@login_required
def registrar_pago_parcial(deuda_id):
    try:
        deuda = Deuda.query.get_or_404(deuda_id)
        cliente_id = request.form.get('cliente_id')
        
        # Obtener datos del formulario
        monto = float(request.form.get('monto'))
        descripcion = request.form.get('descripcion', 'Pago parcial')
        
        # Calcular saldo pendiente
        saldo_pendiente = deuda.saldo_pendiente  # Necesitarías implementar esta propiedad
        
        # Validaciones
        if monto <= 0:
            flash('El monto debe ser mayor a cero', 'danger')
            return redirect(url_for('gestion_deudas', cliente_id=cliente_id))
        
        if monto > saldo_pendiente:
            flash(f'El monto no puede exceder el saldo pendiente (${saldo_pendiente:.2f})', 'danger')
            return redirect(url_for('gestion_deudas', cliente_id=cliente_id))
        
        # Crear pago parcial
        pago = PagoParcial(
            deuda_id=deuda_id,
            monto_usd=monto,
            descripcion=descripcion
        )
        db.session.add(pago)
        
        # Verificar si la deuda queda saldada
        nuevo_saldo = saldo_pendiente - monto
        if nuevo_saldo <= 0.01:  # Tolerancia decimal
            deuda.estado = 'pagada'
        
        db.session.commit()
        
        flash('Pago parcial registrado exitosamente', 'success')
        return redirect(url_for('gestion_deudas', cliente_id=cliente_id))
    except Exception as e:
        print(f"Error al registrar pago parcial: {e}")
        flash('Error al registrar el pago', 'danger')
        return redirect(url_for('dashboard'))

from wtforms import PasswordField
from wtforms.validators import DataRequired, EqualTo

class ChangePasswordForm(FlaskForm):
    old_password = PasswordField('Contraseña actual', validators=[DataRequired()])
    new_password = PasswordField('Nueva contraseña', validators=[DataRequired()])
    confirm_password = PasswordField('Confirmar nueva contraseña', validators=[
        DataRequired(),
        EqualTo('new_password', message='Las contraseñas deben coincidir')
    ])
    submit = SubmitField('Cambiar contraseña')

@app.route('/change_password', methods=['GET', 'POST'])
@login_required
def change_password():
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

@app.route('/eliminar_producto_temp/<int:index>', methods=['POST'])
@login_required
def eliminar_producto_temp(index):
    if 'productos_deuda' in session and 0 <= index < len(session['productos_deuda']):
        session['productos_deuda'].pop(index)
        session.modified = True
    return redirect(url_for('registrar_deuda'))

@app.route('/marcar_pagada/<int:id>', methods=['POST'])
@login_required
def marcar_pagada(id):
    deuda = Deuda.query.get_or_404(id)
    deuda.estado = 'pagada'
    db.session.commit()
    flash('Deuda marcada como pagada', 'success')
    return redirect(url_for('consultar_deudas'))

@app.route('/eliminar_deuda/<int:id>', methods=['POST'])
@login_required
def eliminar_deuda(id):
    deuda = Deuda.query.get_or_404(id)
    
    # Eliminar productos asociados y pagos
    ProductoDeuda.query.filter_by(deuda_id=id).delete()
    PagoParcial.query.filter_by(deuda_id=id).delete()
    
    # Eliminar la deuda
    db.session.delete(deuda)
    db.session.commit()
    
    flash('Deuda eliminada correctamente', 'success')
    return redirect(url_for('consultar_deudas'))

@app.route('/procesar_pedido/<int:pedido_id>', methods=['POST'])
@login_required
def procesar_pedido(pedido_id):
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
    db.session.commit()
    
    flash('Cantidad actualizada', 'success')
    return redirect(url_for('editar_pedido', pedido_id=item.pedido_id))

@app.route('/eliminar_item_pedido/<int:item_id>', methods=['POST'])
@login_required
def eliminar_item_pedido(item_id):
    item = ItemPedido.query.get_or_404(item_id)
    pedido_id = item.pedido_id
    
    # Restaurar stock
    producto = Producto.query.get(item.producto_id)
    producto.cantidad += item.cantidad
    
    # Eliminar item
    db.session.delete(item)
    db.session.commit()
    
    flash('Producto eliminado del pedido', 'success')
    return redirect(url_for('editar_pedido', pedido_id=pedido_id))

@app.route('/descargar_factura/<int:deuda_id>')
@login_required
def descargar_factura(deuda_id):
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

# Ver carrito
@app.route('/cart')
def view_cart():
    cart = session.get('cart', {})
    cart_items = []
    total = 0
    
    for product_id, item in cart.items():
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

# Añadir al carrito
@app.route('/add_to_cart/<int:product_id>', methods=['POST'])
def add_to_cart(product_id):
    quantity = int(request.form.get('quantity', 1))
    producto = Producto.query.get_or_404(product_id)
    
    # Verificar stock
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

# Actualizar carrito
@app.route('/update_cart_quantity/<int:product_id>', methods=['POST'])
def update_cart_quantity(product_id):
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

# Eliminar del carrito
@app.route('/remove_from_cart/<int:product_id>', methods=['POST'])
def remove_from_cart(product_id):
    if 'cart' in session and str(product_id) in session['cart']:
        del session['cart'][str(product_id)]
        session.modified = True
        flash('Producto eliminado del carrito', 'success')
    return redirect(url_for('view_cart'))

# Formulario para checkout
from wtforms import StringField, SubmitField, TextAreaField
class CheckoutForm(FlaskForm):
    nombre = StringField('Nombre', validators=[DataRequired()])
    direccion = StringField('Dirección', validators=[DataRequired()])
    telefono = StringField('Teléfono', validators=[DataRequired()])
    email = StringField('Email', validators=[DataRequired()])
    notas = TextAreaField('Notas')
    submit = SubmitField('Realizar pedido')

@app.route('/checkout', methods=['GET', 'POST'])
def checkout():
    cart = session.get('cart', {})
    if not cart:
        flash('Tu carrito está vacío', 'warning')
        return redirect(url_for('index'))
    
    cart_items = []
    total = 0
    
    for product_id, item in cart.items():
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
    
    if form.validate_on_submit():
        try:
            # Crear pedido
            pedido = Pedido(
                cliente_nombre=form.nombre.data,
                cliente_direccion=form.direccion.data,
                cliente_telefono=form.telefono.data,
                cliente_email=form.email.data,
                total=total,
                notas=form.notas.data
            )
            db.session.add(pedido)
            db.session.flush()
            
            # Crear items del pedido
            for item in cart_items:
                item_pedido = ItemPedido(
                    pedido_id=pedido.id,
                    producto_id=item['id'],
                    producto_nombre=item['name'],
                    precio=item['price'],
                    cantidad=item['quantity']
                )
                db.session.add(item_pedido)
                
                # Actualizar stock
                producto = Producto.query.get(item['id'])
                producto.cantidad -= item['quantity']
            
            db.session.commit()
            
            # Vaciar carrito
            session.pop('cart', None)
            
            flash('Pedido realizado con éxito. ¡Gracias!', 'success')
            return redirect(url_for('index'))
        except Exception as e:
            print(f"Error al realizar el pedido: {e}")
            flash('Error al procesar el pedido', 'danger')
    
    return render_template('checkout.html', form=form, total=total, cart_items=cart_items)

@app.route('/pedidos')
@login_required
def listar_pedidos():
    pedidos = Pedido.query.order_by(Pedido.fecha.desc()).all()
    return render_template('pedidos.html', pedidos=pedidos, form=EmptyForm())

@app.route('/pedido/<int:pedido_id>')
@login_required
def ver_pedido(pedido_id):
    pedido = Pedido.query.get_or_404(pedido_id)
    items = ItemPedido.query.filter_by(pedido_id=pedido_id).all()
    return render_template('detalle_pedido.html', pedido=pedido, items=items)

def obtener_saldo_pendiente(deuda_id):
    deuda = Deuda.query.get_or_404(deuda_id)
    
    # Calcular total de productos
    total_productos = 0
    for pd in deuda.productos:
        producto = Producto.query.get(pd.producto_id)
        if producto:
            total_productos += producto.precio * pd.cantidad
    
    # Calcular total de pagos
    total_pagos = sum(p.monto_usd for p in deuda.pagos)
    
    return round(total_productos - total_pagos, 2)

@app.route('/categorias/<categoria>')
def productos_por_categoria(categoria):
    if categoria == 'todos':
        productos = Producto.query.filter(Producto.cantidad > 0).all()
    else:
        productos = Producto.query.filter(
            Producto.categoria == categoria,
            Producto.cantidad > 0
        ).all()
    
    # Obtener todas las categorías únicas
    categorias = db.session.query(Producto.categoria).distinct().all()
    categorias = [cat[0] for cat in categorias if cat[0] is not None]
    
    return render_template('index.html', productos=productos, 
                          categorias=sorted(categorias), 
                          categoria_actual=categoria,
                          form=ConsultaDeudaForm())

# Formulario para Empresa
from wtforms import StringField, SubmitField
class EmpresaForm(FlaskForm):
    nombre = StringField('Nombre', validators=[DataRequired()])
    direccion = StringField('Dirección', validators=[DataRequired()])
    telefono = StringField('Teléfono', validators=[DataRequired()])
    facebook = StringField('Facebook')
    instagram = StringField('Instagram')
    twitter = StringField('Twitter')
    logo_url = StringField('Logo URL')
    submit = SubmitField('Guardar')

# Ruta para mi cuenta (configuración de empresa)
@app.route('/mi_cuenta', methods=['GET', 'POST'])
@login_required
def mi_cuenta():
    # Obtener o crear información de empresa
    empresa = Empresa.query.first()
    if not empresa:
        empresa = Empresa()
        db.session.add(empresa)
        db.session.commit()
    
    form = EmpresaForm()
    
    # Cargar datos existentes
    if request.method == 'GET':
        form.nombre.data = empresa.nombre
        form.direccion.data = empresa.direccion
        form.telefono.data = empresa.telefono
        form.facebook.data = empresa.facebook
        form.instagram.data = empresa.instagram
        form.twitter.data = empresa.twitter
        form.logo_url.data = empresa.logo_url
    
    if form.validate_on_submit():
        # Actualizar información
        empresa.nombre = form.nombre.data
        empresa.direccion = form.direccion.data
        empresa.telefono = form.telefono.data
        empresa.facebook = form.facebook.data
        empresa.instagram = form.instagram.data
        empresa.twitter = form.twitter.data
        empresa.logo_url = form.logo_url.data
        
        db.session.commit()
        flash('Información de la empresa actualizada correctamente', 'success')
        return redirect(url_for('mi_cuenta'))
    
    return render_template('mi_cuenta.html', form=form, empresa=empresa)

# Inyectar datos de empresa en todas las plantillas
@app.context_processor
def inject_empresa():
    empresa = Empresa.query.first()
    return {'empresa': empresa}

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)
