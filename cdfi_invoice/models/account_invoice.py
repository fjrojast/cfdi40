# -*- coding: utf-8 -*-

import base64
import json
import requests
import datetime
from lxml import etree

from odoo import fields, models, api,_ 
import odoo.addons.decimal_precision as dp
from odoo.exceptions import UserError, Warning

from reportlab.graphics.barcode import createBarcodeDrawing
from reportlab.lib.units import mm
from . import amount_to_text_es_MX
import pytz

import logging
_logger = logging.getLogger(__name__)

class AccountMove(models.Model):
    _inherit = 'account.move'

    factura_cfdi = fields.Boolean('Factura CFDI')
    tipo_comprobante = fields.Selection(
        selection=[('I', 'Ingreso'), 
                   ('E', 'Egreso'),
                   ('T', 'Traslado'),
                  ],
        string=_('Tipo de comprobante'),
    )
    forma_pago = fields.Selection(
        selection=[('01', '01 - Efectivo'), 
                   ('02', '02 - Cheque nominativo'), 
                   ('03', '03 - Transferencia electrónica de fondos'),
                   ('04', '04 - Tarjeta de Crédito'), 
                   ('05', '05 - Monedero electrónico'),
                   ('06', '06 - Dinero electrónico'), 
                   ('08', '08 - Vales de despensa'), 
                   ('12', '12 - Dación en pago'), 
                   ('13', '13 - Pago por subrogación'), 
                   ('14', '14 - Pago por consignación'), 
                   ('15', '15 - Condonación'), 
                   ('17', '17 - Compensación'), 
                   ('23', '23 - Novación'), 
                   ('24', '24 - Confusión'), 
                   ('25', '25 - Remisión de deuda'), 
                   ('26', '26 - Prescripción o caducidad'), 
                   ('27', '27 - A satisfacción del acreedor'), 
                   ('28', '28 - Tarjeta de débito'), 
                   ('29', '29 - Tarjeta de servicios'), 
                   ('30', '30 - Aplicación de anticipos'), 
                   ('31', '31 - Intermediario pagos'),
                   ('99', '99 - Por definir'),],
        string=_('Forma de pago'),
    )
    methodo_pago = fields.Selection(
        selection=[('PUE', _('Pago en una sola exhibición')),
                   ('PPD', _('Pago en parcialidades o diferido')),],
                   string=_('Método de pago'), 
    )
    uso_cfdi = fields.Selection(
        selection=[('G01', _('Adquisición de mercancías')),
                   ('G02', _('Devoluciones, descuentos o bonificaciones')),
                   ('G03', _('Gastos en general')),
                   ('I01', _('Construcciones')),
                   ('I02', _('Mobiliario y equipo de oficina por inversiones')),
                   ('I03', _('Equipo de transporte')),
                   ('I04', _('Equipo de cómputo y accesorios')),
                   ('I05', _('Dados, troqueles, moldes, matrices y herramental')),
                   ('I06', _('Comunicacion telefónica')),
                   ('I07', _('Comunicación Satelital')),
                   ('I08', _('Otra maquinaria y equipo')),
                   ('D01', _('Honorarios médicos, dentales y gastos hospitalarios')),
                   ('D02', _('Gastos médicos por incapacidad o discapacidad')),
                   ('D03', _('Gastos funerales')),
                   ('D04', _('Donativos')),
                   ('D05', _('Intereses reales efectivamente pagados por créditos hipotecarios (casa habitación).')),
                   ('D06', _('Aportaciones voluntarias al SAR.')),
                   ('D07', _('Primas por seguros de gastos médicos')),
                   ('D08', _('Gastos de transportación escolar obligatoria')),
                   ('D09', _('Depósitos en cuentas para el ahorro, primas que tengan como base planes de pensiones')),
                   ('D10', _('Pagos por servicios educativos (colegiaturas)')),
                   ('S01', _('Sin efectos fiscales')),
                   ('CP01', _('Pagos')),
                   ('CN01', _('Nómina')),
                   ('P01', _('Por definir')),],
        string=_('Uso CFDI (cliente)'),
    )
    estado_factura = fields.Selection(
        selection=[('factura_no_generada', 'Factura no generada'), ('factura_correcta', 'Factura correcta'), 
                   ('solicitud_cancelar', 'Cancelación en proceso'),('factura_cancelada', 'Factura cancelada'),
                   ('solicitud_rechazada', 'Cancelación rechazada')],
        string=_('Estado de factura'),
        default='factura_no_generada',
        readonly=True
    )
    pdf_cdfi_invoice = fields.Binary("CDFI Invoice")
    qrcode_image = fields.Binary("QRCode")
    numero_cetificado = fields.Char(string=_('Numero de cetificado'))
    cetificaso_sat = fields.Char(string=_('Cetificao SAT'))
    folio_fiscal = fields.Char(string=_('Folio Fiscal'), readonly=True)
    fecha_certificacion = fields.Char(string=_('Fecha y Hora Certificación'))
    cadena_origenal = fields.Char(string=_('Cadena Origenal del Complemento digital de SAT'))
    selo_digital_cdfi = fields.Char(string=_('Selo Digital del CDFI'))
    selo_sat = fields.Char(string=_('Selo del SAT'))
    moneda = fields.Char(string=_('Moneda'))
    tipocambio = fields.Char(string=_('TipoCambio'))
    jurnal_type=fields.Selection('Journal Type', related='journal_id.type', store=True)
    #folio = fields.Char(string=_('Folio'))
    #version = fields.Char(string=_('Version'))
    number_folio = fields.Char(string=_('Folio'), compute='_get_number_folio')
    amount_to_text = fields.Char('Amount to Text', compute='_get_amount_to_text',
                                 size=256, 
                                 help='Amount of the invoice in letter')
    qr_value = fields.Char(string=_('QR Code Value'))
    invoice_datetime = fields.Char(string=_('11/12/17 12:34:12'))
    fecha_factura = fields.Datetime(string=_('Fecha Factura'))
    #serie_emisor = fields.Char(string=_('A'))
    tipo_relacion = fields.Selection(
        selection=[('01', 'Nota de crédito de los documentos relacionados'), 
                   ('02', 'Nota de débito de los documentos relacionados'), 
                   ('03', 'Devolución de mercancía sobre facturas o traslados previos'),
                   ('04', 'Sustitución de los CFDI previos'), 
                   ('05', 'Traslados de mercancías facturados previamente'),
                   ('06', 'Factura generada por los traslados previos'), 
                   ('07', 'CFDI por aplicación de anticipo'),],
        string=_('Tipo relación'),
    )
    uuid_relacionado = fields.Char(string=_('CFDI Relacionado'))
    confirmacion = fields.Char(string=_('Confirmación'))
    facatradquirente = fields.Char(string=_('Fac Atr Adquirente'))
    exportacion = fields.Selection(
        selection=[('01', 'No aplica'), 
                   ('02', 'Definitiva'), 
                   ('03', 'Temporal'),],
        string=_('Exportacion'), default = '01',
    )
    proceso_timbrado = fields.Boolean(string=_('Proceso de timbrado'))

    @api.model
    def _reverse_move_vals(self,default_values, cancel=True):
        values = super(AccountMove, self)._reverse_move_vals(default_values, cancel)
        if self.estado_factura == 'factura_correcta':
            values['uuid_relacionado'] = self.folio_fiscal
            values['methodo_pago'] = self.methodo_pago
            values['forma_pago'] = self.forma_pago
            values['tipo_comprobante'] = 'E'
            values['uso_cfdi'] = 'G02'
            values['tipo_relacion'] = '01'
            values['fecha_factura'] = None
            values['qrcode_image'] = None
            values['numero_cetificado'] = None
            values['cetificaso_sat'] = None
            values['selo_digital_cdfi'] = None
            values['fecha_factura'] = None
            values['folio_fiscal'] = None
            values['invoice_datetime'] = None
            values['estado_factura'] = None
            values['factura_cfdi'] = False
        return values

    @api.returns('self', lambda value: value.id)
    def copy(self, default=None):
        default = dict(default or {})
        if self.estado_factura == 'factura_correcta' or self.estado_factura == 'factura_cancelada':
            default['estado_factura'] = 'factura_no_generada'
            default['folio_fiscal'] = ''
            default['fecha_factura'] = None
            default['factura_cfdi'] = False
        return super(AccountMove, self).copy(default=default)
    
    @api.depends('name')
    def _get_number_folio(self):
        for record in self:
            if record.name:
                record.number_folio = record.name.replace('INV','').replace('/','')
            
    @api.depends('amount_total', 'currency_id')
    def _get_amount_to_text(self):
        for record in self:
            record.amount_to_text = amount_to_text_es_MX.get_amount_to_text(record, record.amount_total, 'es_cheque', record.currency_id.name)
        
    @api.model
    def _get_amount_2_text(self, amount_total):
        return amount_to_text_es_MX.get_amount_to_text(self, amount_total, 'es_cheque', self.currency_id.name)

    
    @api.onchange('partner_id')
    def _get_uso_cfdi(self):
        if self.partner_id:
            values = {
                'uso_cfdi': self.partner_id.uso_cfdi
                }
            self.update(values)

    
    @api.onchange('invoice_payment_term_id')
    def _get_metodo_pago(self):
        if self.invoice_payment_term_id:
            if self.invoice_payment_term_id.methodo_pago == 'PPD':
                values = {
                 'methodo_pago': self.invoice_payment_term_id.methodo_pago,
                 'forma_pago': '99'
                }
            else:
                values = {
                    'methodo_pago': self.invoice_payment_term_id.methodo_pago,
                    'forma_pago': False
                    }
        else:
            values = {
                'methodo_pago': False,
                'forma_pago': False
                }
        self.update(values)
    
    @api.model
    def to_json(self):
        if self.partner_id.vat == 'XAXX010101000':
            nombre = 'PUBLICO GENERAL'
        else:
            nombre = self.clean_text(self.partner_id.name.upper())

        no_decimales = self.currency_id.no_decimales
        no_decimales_prod = self.currency_id.decimal_places
        no_decimales_tc = self.currency_id.no_decimales_tc

        #corregir hora
        timezone = self._context.get('tz')
        if not timezone:
            timezone = self.journal_id.tz or self.env.user.partner_id.tz or 'America/Mexico_City'
        #timezone = tools.ustr(timezone).encode('utf-8')

        local = pytz.timezone(timezone)
        if not self.fecha_factura:
           naive_from = datetime.datetime.now()
        else:
           naive_from = self.fecha_factura
        local_dt_from = naive_from.replace(tzinfo=pytz.UTC).astimezone(local)
        date_from = local_dt_from.strftime ("%Y-%m-%dT%H:%M:%S")

        if self.currency_id.name == 'MXN':
           tipocambio = 1
        else:
           tipocambio = self.set_decimals(1 / self.currency_id.with_context(date=self.invoice_date).rate, no_decimales_tc)

        self.check_cfdi_values()

        request_params = {
                'factura': {
                      'serie': self.journal_id.serie_diario or self.company_id.serie_factura,
                      'folio': self.name.replace('INV','').replace('/',''),
                      'fecha_expedicion': date_from,
                      'forma_pago': self.forma_pago,
                      'subtotal': self.amount_untaxed,
                      'descuento': 0,
                      'moneda': self.currency_id.name,
                      'tipocambio': tipocambio,
                      'total': self.amount_total,
                      'tipocomprobante': self.tipo_comprobante,
                      'metodo_pago': self.methodo_pago,
                      'LugarExpedicion': self.journal_id.codigo_postal or self.company_id.zip,
                      'Confirmacion': self.confirmacion,
                      'Exportacion': self.exportacion,
                },
                'emisor': {
                      'rfc': self.company_id.vat.upper(),
                      'nombre': self.clean_text(self.company_id.nombre_fiscal.upper()),
                      'RegimenFiscal': self.company_id.regimen_fiscal,
                      'FacAtrAdquirente': self.facatradquirente,
                },
                'receptor': {
                      'nombre': nombre,
                      'rfc': self.partner_id.vat.upper(),
                      'ResidenciaFiscal': self.partner_id.residencia_fiscal,
                      'NumRegIdTrib': self.partner_id.registro_tributario,
                      'UsoCFDI': self.uso_cfdi,
                      'RegimenFiscalReceptor': self.partner_id.regimen_fiscal,
                      'DomicilioFiscalReceptor': self.partner_id.zip,
                },
                'informacion': {
                      'cfdi': '4.0',
                      'sistema': 'odoo14',
                      'version': '1',
                      'api_key': self.company_id.proveedor_timbrado,
                      'modo_prueba': self.company_id.modo_prueba,
                },
        }

        if self.uuid_relacionado:
           cfdi_relacionado = []
           uuids = self.uuid_relacionado.replace(' ','').split(',')
           for uuid in uuids:
                cfdi_relacionado.append({
                      'uuid': uuid,
                })
           request_params.update({'CfdisRelacionados': {'UUID': cfdi_relacionado, 'TipoRelacion':self.tipo_relacion }})

        amount_total = 0.0
        amount_untaxed = 0.0
        subtotal = 0
        total = 0
        discount = 0
        tras_tot = 0
        ret_tot = 0
        tax_grouped_tras = {}
        tax_grouped_ret = {}
        tax_local_ret = []
        tax_local_tras = []
        tax_local_ret_tot = 0
        tax_local_tras_tot = 0
        items = {'numerodepartidas': len(self.invoice_line_ids)}
        invoice_lines = []
        for line in self.invoice_line_ids:
            if not line.product_id or line.display_type in ('line_section', 'line_note'):
                continue

            if not line.product_id.clave_producto:
                raise UserError(_('El producto %s no tiene clave del SAT configurado.') % (line.product_id.name))
            if not line.product_id.cat_unidad_medida.clave:
                raise UserError(_('El producto %s no tiene unidad de medida del SAT configurado.') % (line.product_id.name))

            price_wo_discount = round(line.price_unit * (1 - (line.discount / 100.0)), no_decimales_prod)

            taxes_prod = line.tax_ids.compute_all(price_wo_discount, line.currency_id, line.quantity, product=line.product_id, partner=line.move_id.partner_id)
            tax_ret = []
            tax_tras = []
            tax_items = {}
            tax_included = 0
            for taxes in taxes_prod['taxes']:
                tax = self.env['account.tax'].browse(taxes['id'])
                if not tax.impuesto:
                   raise UserError(_('El impusto %s no tiene clave del SAT configurado.') % (tax.name))
                if not tax.tipo_factor:
                   raise UserError(_('El impuesto %s no tiene tipo de factor del SAT configurado.') % (tax.name))
                if tax.impuesto != '004':
                   key = tax['id']
                   if tax.price_include or tax.amount_type == 'division':
                       tax_included += taxes['amount']

                   if taxes['amount'] >= 0.0:
                      if tax.tipo_factor == 'Exento':
                         tax_tras.append({'Base': self.set_decimals(taxes['base'], no_decimales_prod),
                                           'Impuesto': tax.impuesto,
                                           'TipoFactor': tax.tipo_factor,})
                      else:
                         tax_tras.append({'Base': self.set_decimals(taxes['base'], no_decimales_prod),
                                           'Impuesto': tax.impuesto,
                                           'TipoFactor': tax.tipo_factor,
                                           'TasaOCuota': self.set_decimals(tax.amount / 100.0,6),
                                           'Importe': self.set_decimals(taxes['amount'], no_decimales_prod),})
                      tras_tot += taxes['amount']
                      val = {'tax_id': tax['id'],
                             'base': taxes['base'],
                             'amount': taxes['amount'],}
                      if key not in tax_grouped_tras:
                          tax_grouped_tras[key] = val
                      else:
                          tax_grouped_tras[key]['base'] += taxes['base']
                          tax_grouped_tras[key]['amount'] += taxes['amount']
                   else:
                      tax_ret.append({'Base': self.set_decimals(taxes['base'], no_decimales_prod),
                                      'Impuesto': tax.impuesto,
                                      'TipoFactor': tax.tipo_factor,
                                      'TasaOCuota': self.set_decimals(tax.amount / 100.0 * -1, 6),
                                      'Importe': self.set_decimals(taxes['amount'] * -1, no_decimales_prod),})
                      ret_tot += taxes['amount'] * -1
                      val = {'tax_id': tax['id'],
                             'base': taxes['base'],
                             'amount': taxes['amount'],}
                      if key not in tax_grouped_ret:
                          tax_grouped_ret[key] = val
                      else:
                          tax_grouped_tras[key]['base'] += taxes['base']
                          tax_grouped_ret[key]['amount'] += taxes['amount']
                else: #impuestos locales
                   if taxes['amount'] >= 0.0:
                      tax_local_tras_tot += taxes['amount']
                      tax_local_tras.append({'ImpLocTrasladado': tax.impuesto_local,
                                             'TasadeTraslado': self.set_decimals(tax.amount / 100.0,6),
                                             'Importe': self.set_decimals(taxes['amount'], no_decimales),})
                   else:
                      tax_local_ret_tot += taxes['amount']
                      tax_local_ret.append({'ImpLocRetenido': tax.impuesto_local,
                                            'TasadeRetencion': self.set_decimals(tax.amount / 100.0 * -1,6),
                                            'Importe': self.set_decimals(taxes['amount'] * -1, no_decimales),})

            if tax_tras:
               tax_items.update({'Traslados': tax_tras})
            if tax_ret:
               tax_items.update({'Retenciones': tax_ret})

            total_wo_discount = round(line.price_unit * line.quantity - tax_included, no_decimales_prod)
            discount_prod = round(total_wo_discount - line.price_subtotal, no_decimales_prod) if line.discount else 0
            precio_unitario = round(total_wo_discount / line.quantity, no_decimales_prod)
            subtotal += total_wo_discount
            discount += discount_prod

            #probar con varios pedimentos
            pedimentos = []
            if line.pedimento:
                pedimentos = line.pedimento.replace(' ','').split(',')
                for pedimento in pedimentos:
                   no_pedimento = pedimento[0:2] + '  ' + pedimento[2:4] + '  ' + pedimento[4:8] + '  ' + pedimento[8:]
                   pedimentos.append({'NumeroPedimento': no_pedimento})

            product_string = line.product_id.code and line.product_id.code[:100] or ''
            if product_string == '':
               if line.name.find(']') > 0:
                  product_string = line.name[line.name.find('[')+len('['):line.name.find(']')] or ''
            description = line.name
            if line.name.find(']') > 0:
                 description = line.name[line.name.find(']') + 2:]

            if self.tipo_comprobante == 'T':
                invoice_lines.append({'cantidad': self.set_decimals(line.quantity,6),
                                      'unidad': line.product_id.cat_unidad_medida.descripcion,
                                      'NoIdentificacion': self.clean_text(product_string),
                                      'valorunitario': self.set_decimals(precio_unitario, no_decimales_prod),
                                      'importe': self.set_decimals(total_wo_discount, no_decimales_prod),
                                      'descripcion': self.clean_text(description),
                                      'ClaveProdServ': line.product_id.clave_producto,
                                      'ObjetoImp': line.product_id.objetoimp,
                                      'ClaveUnidad': line.product_id.cat_unidad_medida.clave})
            else:
                invoice_lines.append({'cantidad': self.set_decimals(line.quantity,6),
                                      'unidad': line.product_id.cat_unidad_medida.descripcion,
                                      'NoIdentificacion': self.clean_text(product_string),
                                      'valorunitario': self.set_decimals(precio_unitario, no_decimales_prod),
                                      'importe': self.set_decimals(total_wo_discount, no_decimales_prod),
                                      'descripcion': self.clean_text(description),
                                      'ClaveProdServ': line.product_id.clave_producto,
                                      'ClaveUnidad': line.product_id.cat_unidad_medida.clave,
                                      'Impuestos': tax_items,
                                      'Descuento': self.set_decimals(discount_prod, no_decimales_prod),
                                      'ObjetoImp': line.product_id.objetoimp,
                                      'InformacionAduanera': pedimentos and pedimentos or '',})
            if line.predial:
                invoice_lines.append({'predial': line.predial})

        tras_tot = round(tras_tot, no_decimales)
        ret_tot = round(ret_tot, no_decimales)
        tax_local_tras_tot = round(tax_local_tras_tot, no_decimales)
        tax_local_ret_tot = round(tax_local_ret_tot, no_decimales)
        discount = round(discount, no_decimales)
        if tax_grouped_tras or tax_grouped_ret:
                impuestos = {}
                retenciones = []
                traslados = []
                if tax_grouped_tras:
                   for line in tax_grouped_tras.values():
                       tax = self.env['account.tax'].browse(line['tax_id'])
                       if tax.tipo_factor != 'Exento':
                          traslados.append({'impuesto': tax.impuesto,
                                         'TipoFactor': tax.tipo_factor,
                                         'tasa': self.set_decimals(tax.amount / 100.0, 6), # if tax.tipo_factor != 'Exento' else '',
                                         'importe': self.set_decimals(line['amount'], no_decimales), # if tax.tipo_factor != 'Exento' else '',
                                         'base': self.set_decimals(line['base'], no_decimales),
                                         })
                   impuestos.update({'translados': traslados, 'TotalImpuestosTrasladados': self.set_decimals(tras_tot, no_decimales)})
                if tax_grouped_ret:
                   for line in tax_grouped_ret.values():
                       tax = self.env['account.tax'].browse(line['tax_id'])
                       retenciones.append({'impuesto': tax.impuesto,
                                         'importe': self.set_decimals(line['amount'] * -1, no_decimales),
                                         })
                   impuestos.update({'retenciones': retenciones, 'TotalImpuestosRetenidos': self.set_decimals(ret_tot, no_decimales)})
                request_params.update({'impuestos': impuestos})

        if tax_local_ret or tax_local_tras:
           if tax_local_tras and not tax_local_ret:
               request_params.update({'implocal10': {'TotaldeTraslados': tax_local_tras_tot, 'TotaldeRetenciones': tax_local_ret_tot, 'TrasladosLocales': tax_local_tras,}})
           if tax_local_ret and not tax_local_tras:
               request_params.update({'implocal10': {'TotaldeTraslados': tax_local_tras_tot, 'TotaldeRetenciones': tax_local_ret_tot * -1, 'RetencionesLocales': tax_local_ret,}})
           if tax_local_ret and tax_local_tras:
               request_params.update({'implocal10': {'TotaldeTraslados': tax_local_tras_tot, 'TotaldeRetenciones': tax_local_ret_tot * -1, 'TrasladosLocales': tax_local_tras, 'RetencionesLocales': tax_local_ret,}})

        if self.tipo_comprobante == 'T':
            request_params['factura'].update({'subtotal': '0.00','total': '0.00'})
        else:
            request_params['factura'].update({'descuento': self.set_decimals(discount, no_decimales),
                                              'subtotal': self.set_decimals(subtotal, no_decimales),
                                              'total':  self.set_decimals(subtotal + tras_tot - ret_tot - discount + tax_local_ret_tot + tax_local_tras_tot, no_decimales)})

        request_params.update({'conceptos': invoice_lines})

        if not self.company_id.archivo_cer:
            raise UserError(_('El archivo del certificado .cer no se encuentra.'))
        if not self.company_id.archivo_key:
            raise UserError(_('El archivo del certificado .key no se encuentra.'))
        if not self.company_id.contrasena:
            raise UserError(_('La contraseña del certificado no se encuentra.'))
        archivo_cer = self.company_id.archivo_cer
        archivo_key = self.company_id.archivo_key
        request_params.update({
            'certificados': {
                'archivo_cer': archivo_cer.decode("utf-8"),
                'archivo_key': archivo_key.decode("utf-8"),
                'contrasena': self.company_id.contrasena,
            }})

        #_logger.info('xml: ', json.dumps(request_params))
        return request_params

    def set_decimals(self, amount, precision):
        if amount is None or amount is False:
            return None
        return '%.*f' % (precision, amount)

    def clean_text(self, text):
        clean_text = text.replace('\n', ' ').replace('\\', ' ').replace('-', ' ').replace('/', ' ').replace('|', ' ')
        clean_text = clean_text.replace(',', ' ').replace(';', ' ').replace('>', ' ').replace('<', ' ')
        return clean_text[:1000]

    def check_cfdi_values(self):
        if not self.company_id.vat:
            raise UserError(_('El emisor no tiene RFC configurado.'))
        if not self.company_id.name:
            raise UserError(_('El emisor no tiene nombre configurado.'))
        if not self.partner_id.vat:
            raise UserError(_('El receptor no tiene RFC configurado.'))
        if not self.uso_cfdi:
            raise UserError(_('La factura no tiene uso de cfdi configurado.'))
        if not self.tipo_comprobante:
            raise UserError(_('El emisor no tiene tipo de comprobante configurado.'))
        if self.tipo_comprobante != 'T' and not self.methodo_pago:
            raise UserError(_('La factura no tiene método de pago configurado.'))
        if self.tipo_comprobante != 'T' and not self.forma_pago:
            raise UserError(_('La factura no tiene forma de pago configurado.'))
        if not self.company_id.regimen_fiscal:
            raise UserError(_('El emisor no régimen fiscal configurado.'))
        if not self.journal_id.codigo_postal and not self.company_id.zip:
            raise UserError(_('El emisor no tiene código postal configurado.'))

    def _set_data_from_xml(self, xml_invoice):
        if not xml_invoice:
            return None
        NSMAP = {
            'xsi': 'http://www.w3.org/2001/XMLSchema-instance',
            'cfdi': 'http://www.sat.gob.mx/cfd/4',
            'tfd': 'http://www.sat.gob.mx/TimbreFiscalDigital',
        }

        xml_data = etree.fromstring(xml_invoice)
        Complemento = xml_data.findall('cfdi:Complemento', NSMAP)

        for complementos in Complemento:
            TimbreFiscalDigital = complementos.find('tfd:TimbreFiscalDigital', NSMAP)
            if TimbreFiscalDigital:
                break

        self.tipocambio = xml_data.find('TipoCambio') and xml_data.attrib['TipoCambio'] or '1'
        self.moneda = xml_data.attrib['Moneda']
        self.numero_cetificado = xml_data.attrib['NoCertificado']
        self.cetificaso_sat = TimbreFiscalDigital.attrib['NoCertificadoSAT']
        self.fecha_certificacion = TimbreFiscalDigital.attrib['FechaTimbrado']
        self.selo_digital_cdfi = TimbreFiscalDigital.attrib['SelloCFD']
        self.selo_sat = TimbreFiscalDigital.attrib['SelloSAT']
        self.folio_fiscal = TimbreFiscalDigital.attrib['UUID']
        self.invoice_datetime = xml_data.attrib['Fecha']
        if not self.fecha_factura:
            self.fecha_factura = self.invoice_datetime.replace('T', ' ')
        version = TimbreFiscalDigital.attrib['Version']
        self.cadena_origenal = '||%s|%s|%s|%s|%s||' % (version, self.folio_fiscal, self.fecha_certificacion,
                                                       self.selo_digital_cdfi, self.cetificaso_sat)

        options = {'width': 275 * mm, 'height': 275 * mm}
        amount_str = str(self.amount_total).split('.')
        qr_value = 'https://verificacfdi.facturaelectronica.sat.gob.mx/default.aspx?&id=%s&re=%s&rr=%s&tt=%s.%s&fe=%s' % (
            self.folio_fiscal,
            self.company_id.vat,
            self.partner_id.vat,
            amount_str[0].zfill(10),
            amount_str[1].ljust(6, '0'),
            self.selo_digital_cdfi[-8:],
        )
        self.qr_value = qr_value
        ret_val = createBarcodeDrawing('QR', value=qr_value, **options)
        self.qrcode_image = base64.encodestring(ret_val.asString('jpg'))

    def print_cdfi_invoice(self):
        self.ensure_one()
        #return self.env['report'].get_action(self, 'custom_invoice.cdfi_invoice_report') #modulename.custom_report_coupon 
        filename = 'CDFI_' + self.name.replace('/', '_') + '.pdf'
        return {
                 'type' : 'ir.actions.act_url',
                 'url': '/web/binary/download_document?model=account.move&field=pdf_cdfi_invoice&id=%s&filename=%s'%(self.id, filename),
                 'target': 'self',
                 }
        
    
    def action_cfdi_generate(self):
        # after validate, send invoice data to external system via http post
        for invoice in self:
            if invoice.proceso_timbrado:
                return True
            else:
               invoice.write({'proceso_timbrado': True})
               self.env.cr.commit()
            if invoice.estado_factura == 'factura_correcta':
                if invoice.folio_fiscal:
                    invoice.write({'factura_cfdi': True})
                    return True
                else:
                    raise UserError(_('Error para timbrar factura, Factura ya generada.'))
            if invoice.estado_factura == 'factura_cancelada':
                raise UserError(_('Error para timbrar factura, Factura ya generada y cancelada.'))

            values = invoice.to_json()
            if invoice.company_id.proveedor_timbrado == 'multifactura':
                url = '%s' % ('http://facturacion.itadmin.com.mx/api/invoice')
            elif invoice.company_id.proveedor_timbrado == 'multifactura2':
                url = '%s' % ('http://facturacion2.itadmin.com.mx/api/invoice')
            elif invoice.company_id.proveedor_timbrado == 'multifactura3':
                url = '%s' % ('http://facturacion3.itadmin.com.mx/api/invoice')
            elif invoice.company_id.proveedor_timbrado == 'gecoerp':
                if self.company_id.modo_prueba:
                    url = '%s' % ('https://itadmin.gecoerp.com/invoice/?handler=OdooHandler33')
                else:
                    url = '%s' % ('https://itadmin.gecoerp.com/invoice/?handler=OdooHandler33')
            else:
                raise UserError(_('Error, falta seleccionar el servidor de timbrado en la configuración de la compañía.'))

            try:
                response = requests.post(url,
                                         auth=None, verify=False, data=json.dumps(values),
                                         headers={"Content-type": "application/json"})
            except Exception as e:
                error = str(e)
                invoice.write({'proceso_timbrado': False})
                self.env.cr.commit()
                if "Name or service not known" in error or "Failed to establish a new connection" in error:
                    raise Warning("Servidor fuera de servicio, favor de intentar mas tarde")
                else:
                    raise Warning(error)

            if "Whoops, looks like something went wrong." in response.text:
                invoice.write({'proceso_timbrado': False})
                self.env.cr.commit()
                raise Warning("Error con el servidor de facturación, favor de reportar el error a su persona de soporte. \nNo intente timbrar de nuevo hasta validar que el servicio ha sido restablecido, ya que pudiera timbrar doble alguna factura.")
            else:
                json_response = response.json()
            estado_factura = json_response['estado_factura']
            if estado_factura == 'problemas_factura':
                invoice.write({'proceso_timbrado': False})
                self.env.cr.commit()
                raise UserError(_(json_response['problemas_message']))
            # Receive and stroe XML invoice
            if json_response.get('factura_xml'):
                invoice._set_data_from_xml(base64.b64decode(json_response['factura_xml']))
                file_name = invoice.name.replace('/', '_') + '.xml'
                self.env['ir.attachment'].sudo().create(
                    {
                        'name': file_name,
                        'datas': json_response['factura_xml'],
                        # 'datas_fname': file_name,
                        'res_model': self._name,
                        'res_id': invoice.id,
                        'type': 'binary'
                    })

            invoice.write({'estado_factura': estado_factura,
                           'factura_cfdi': True,
                           'proceso_timbrado': False})
            invoice.message_post(body="CFDI emitido")
        return True

    def action_cfdi_cancel(self):
        for invoice in self:
            if invoice.factura_cfdi:
                if invoice.estado_factura == 'factura_cancelada':
                    pass
                    # raise UserError(_('La factura ya fue cancelada, no puede volver a cancelarse.'))
                if not invoice.company_id.archivo_cer:
                    raise UserError(_('Falta la ruta del archivo .cer'))
                if not invoice.company_id.archivo_key:
                    raise UserError(_('Falta la ruta del archivo .key'))
                archivo_cer = self.company_id.archivo_cer
                archivo_key = self.company_id.archivo_key
                domain = [
                    ('res_id', '=', invoice.id),
                    ('res_model', '=', invoice._name),
                    ('name', '=', invoice.name.replace('/', '_') + '.xml')]
                xml_file = self.env['ir.attachment'].search(domain)[0]
                values = {
                    'rfc': invoice.company_id.vat,
                    'api_key': invoice.company_id.proveedor_timbrado,
                    'uuid': self.folio_fiscal,
                    'folio': self.folio,
                    'serie_factura': invoice.company_id.serie_factura,
                    'modo_prueba': invoice.company_id.modo_prueba,
                    'certificados': {
                        'archivo_cer': archivo_cer.decode("utf-8"),
                        'archivo_key': archivo_key.decode("utf-8"),
                        'contrasena': invoice.company_id.contrasena,
                    },
                    'xml': xml_file.datas.decode("utf-8"),
                          'motivo': self.env.context.get('motivo_cancelacion',False),
                          'foliosustitucion': self.env.context.get('foliosustitucion',''),
                }
                if self.company_id.proveedor_timbrado == 'multifactura':
                    url = '%s' % ('http://facturacion.itadmin.com.mx/api/refund')
                elif invoice.company_id.proveedor_timbrado == 'multifactura2':
                    url = '%s' % ('http://facturacion2.itadmin.com.mx/api/refund')
                elif invoice.company_id.proveedor_timbrado == 'multifactura3':
                    url = '%s' % ('http://facturacion3.itadmin.com.mx/api/refund')
                elif self.company_id.proveedor_timbrado == 'gecoerp':
                    if self.company_id.modo_prueba:
                        url = '%s' % ('https://itadmin.gecoerp.com/refund/?handler=OdooHandler33')
                    else:
                        url = '%s' % ('https://itadmin.gecoerp.com/refund/?handler=OdooHandler33')
                else:
                    raise UserError(_('Error, falta seleccionar el servidor de timbrado en la configuración de la compañía.'))

                try:
                    response = requests.post(url,
                                             auth=None, verify=False, data=json.dumps(values),
                                             headers={"Content-type": "application/json"})
                except Exception as e:
                    error = str(e)
                    if "Name or service not known" in error or "Failed to establish a new connection" in error:
                        raise Warning("Servidor fuera de servicio, favor de intentar mas tarde")
                    else:
                        raise Warning(error)

                if "Whoops, looks like something went wrong." in response.text:
                    raise Warning("Error con el servidor de facturación, favor de reportar el error a su persona de soporte.")

                json_response = response.json()

                log_msg = ''
                if json_response['estado_factura'] == 'problemas_factura':
                    raise UserError(_(json_response['problemas_message']))
                elif json_response['estado_factura'] == 'solicitud_cancelar':
                    # invoice.write({'estado_factura': json_response['estado_factura']})
                    log_msg = "Se solicitó cancelación de CFDI"
                    # raise Warning(_(json_response['problemas_message']))
                elif json_response.get('factura_xml', False):
                    file_name = 'CANCEL_' + invoice.name.replace('/', '_') + '.xml'
                    self.env['ir.attachment'].sudo().create(
                        {
                            'name': file_name,
                            'datas': json_response['factura_xml'],
                            # 'datas_fname': file_name,
                            'res_model': self._name,
                            'res_id': invoice.id,
                            'type': 'binary'
                        })
                    log_msg = "CFDI Cancelado"
                invoice.write({'estado_factura': json_response['estado_factura']})
                invoice.message_post(body=log_msg)
 
 
    
    def force_invoice_send(self):
        for inv in self:
            email_act = inv.action_invoice_sent()
            if email_act and email_act.get('context'):
                email_ctx = email_act['context']
                email_ctx.update(default_email_from=inv.company_id.email)
                inv.with_context(email_ctx).message_post_with_template(email_ctx.get('default_template_id'))
        return True

    @api.model
    def check_cancel_status_by_cron(self):
        domain = [('type', '=', 'out_invoice'),('estado_factura', '=', 'solicitud_cancelar')]
        invoices = self.search(domain, order = 'id')
        for invoice in invoices:
            _logger.info('Solicitando estado de factura %s', invoice.folio_fiscal)
            domain = [
                 ('res_id', '=', invoice.id),
                 ('res_model', '=', invoice._name),
                 ('name', '=', invoice.name.replace('/', '_') + '.xml')]
            xml_file = self.env['ir.attachment'].search(domain, limit=1)
            values = {
                 'rfc': invoice.company_id.vat,
                 'api_key': invoice.company_id.proveedor_timbrado,
                 'modo_prueba': invoice.company_id.modo_prueba,
                 'uuid': invoice.folio_fiscal,
                 'xml': xml_file.datas.decode("utf-8"),
                 }

            if invoice.company_id.proveedor_timbrado == 'multifactura':
                url = '%s' % ('http://facturacion.itadmin.com.mx/api/consulta-cacelar')
            elif invoice.company_id.proveedor_timbrado == 'multifactura2':
                url = '%s' % ('http://facturacion2.itadmin.com.mx/api/consulta-cacelar')
            elif invoice.company_id.proveedor_timbrado == 'multifactura3':
                url = '%s' % ('http://facturacion3.itadmin.com.mx/api/consulta-cacelar')
            elif invoice.company_id.proveedor_timbrado == 'gecoerp':
                url = '%s' % ('http://facturacion.itadmin.com.mx/api/consulta-cacelar')

            try:
               response = requests.post(url, 
                                         auth=None,verify=False, data=json.dumps(values), 
                                         headers={"Content-type": "application/json"})

               if "Whoops, looks like something went wrong." in response.text:
                   _logger.info("Error con el servidor de facturación, favor de reportar el error a su persona de soporte.")
                   return

               json_response = response.json()
               #_logger.info('something ... %s', response.text)
            except Exception as e:
               _logger.info('log de la exception ... %s', response.text)
               json_response = {}
            if not json_response:
               return
            estado_factura = json_response['estado_consulta']
            if estado_factura == 'problemas_consulta':
                _logger.info('Error en la consulta %s', json_response['problemas_message'])
            elif estado_factura == 'consulta_correcta':
                if json_response['factura_xml'] == 'Cancelado':
                    _logger.info('Factura cancelada')
                    _logger.info('EsCancelable: %s', json_response['escancelable'])
                    _logger.info('EstatusCancelacion: %s', json_response['estatuscancelacion'])
                    invoice.action_cfdi_cancel()
                elif json_response['factura_xml'] == 'Vigente':
                    _logger.info('Factura vigente')
                    _logger.info('EsCancelable: %s', json_response['escancelable'])
                    _logger.info('EstatusCancelacion: %s', json_response['estatuscancelacion'])
                    if json_response['estatuscancelacion'] == 'Solicitud rechazada':
                        invoice.estado_factura = 'solicitud_rechazada'
            else:
                _logger.info('Error... %s', response.text)
        return True

    def action_cfdi_rechazada(self):
        for invoice in self:
            if invoice.factura_cfdi:
                if invoice.estado_factura == 'solicitud_rechazada' or invoice.estado_factura == 'solicitud_cancelar':
                    invoice.estado_factura = 'factura_correcta'
                    # raise UserError(_('La factura ya fue cancelada, no puede volver a cancelarse.'))

    def liberar_cfdi(self):
        for invoice in self:
           values = {
                 'command': 'liberar_cfdi',
                 'rfc': invoice.company_id.vat,
                 'folio': invoice.name.replace('INV','').replace('/',''),
                 'serie_factura': invoice.journal_id.serie_diario or invoice.company_id.serie_factura,
                 'archivo_cer': invoice.company_id.archivo_cer.decode("utf-8"),
                 'archivo_key': invoice.company_id.archivo_key.decode("utf-8"),
                 'contrasena': invoice.company_id.contrasena,
                 }
           url=''
           if invoice.company_id.proveedor_timbrado == 'multifactura':
               url = '%s' % ('http://facturacion.itadmin.com.mx/api/command')
           elif invoice.company_id.proveedor_timbrado == 'multifactura2':
               url = '%s' % ('http://facturacion2.itadmin.com.mx/api/command')
           elif invoice.company_id.proveedor_timbrado == 'multifactura3':
               url = '%s' % ('http://facturacion3.itadmin.com.mx/api/command')
           if not url:
               return
           try:
               response = requests.post(url,auth=None,verify=False, data=json.dumps(values),headers={"Content-type": "application/json"})

               if "Whoops, looks like something went wrong." in response.text:
                   raise Warning("Error con el servidor de facturación, favor de reportar el error a su persona de soporte.")

               json_response = response.json()
           except Exception as e:
               print(e)
               json_response = {}

           if not json_response:
               return
           #_logger.info('something ... %s', response.text)

           respuesta = json_response['respuesta']
           message_id = self.env['mymodule.message.wizard'].create({'message': respuesta})
           return {
               'name': 'Respuesta',
               'type': 'ir.actions.act_window',
               'view_mode': 'form',
               'res_model': 'mymodule.message.wizard',
               'res_id': message_id.id,
               'target': 'new'
           }

class MailTemplate(models.Model):
    "Templates for sending email"
    _inherit = 'mail.template'

    
    def generate_email(self, res_ids, fields=None):
        results = super(MailTemplate, self).generate_email(res_ids, fields=fields)
        
        if isinstance(res_ids, (int)):
            res_ids = [res_ids]
        res_ids_to_templates = super(MailTemplate, self).get_email_template(res_ids)

        # templates: res_id -> template; template -> res_ids
        templates_to_res_ids = {}
        for res_id, template in res_ids_to_templates.items():
            templates_to_res_ids.setdefault(template, []).append(res_id)

        for template, template_res_ids in templates_to_res_ids.items():
            if template.report_template and template.report_template.report_name == 'account.report_invoice' \
                                or template.report_template.report_name == 'account.report_invoice_with_payments':
                for res_id in template_res_ids:
                    invoice = self.env[template.model].browse(res_id)
                    if not invoice.factura_cfdi:
                        continue
                    if invoice.estado_factura == 'factura_correcta' or invoice.estado_factura == 'solicitud_cancelar':
                        domain = [
                            ('res_id', '=', invoice.id),
                            ('res_model', '=', invoice._name),
                            ('name', '=', invoice.name.replace('/', '_') + '.xml')]
                        xml_file = self.env['ir.attachment'].search(domain, limit=1)
                        attachments = results[res_id]['attachments'] or []
                        if xml_file:
                           attachments.append(('CDFI_' + invoice.name.replace('/', '_') + '.xml', xml_file.datas))
                    else:
                        domain = [
                            ('res_id', '=', invoice.id),
                            ('res_model', '=', invoice._name),
                            ('name', '=', 'CANCEL_' + invoice.name.replace('/', '_') + '.xml')]
                        xml_file = self.env['ir.attachment'].search(domain, limit=1)
                        attachments = []
                        if xml_file:
                           attachments.append(('CDFI_CANCEL_' + invoice.name.replace('/', '_') + '.xml', xml_file.datas))
                    results[res_id]['attachments'] = attachments
        return results

class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    pedimento = fields.Char('Pedimento')
    predial = fields.Char('No. Predial')
    
    
class AccountPartialReconcile(models.Model):
    _inherit = "account.partial.reconcile"
    
    def unlink(self):
        full_to_unlink = self.env['account.full.reconcile']
        for rec in self:
            if rec.full_reconcile_id:
                full_to_unlink |= rec.full_reconcile_id
        for move in self.env['account.move'].search([('tax_cash_basis_rec_id', 'in', self._ids)]):
            move.tax_cash_basis_rec_id = False
            move.state = 'cancel'
        res = super(AccountPartialReconcile, self).unlink()
        if full_to_unlink:
            full_to_unlink.unlink()
        return res

class MyModuleMessageWizard(models.TransientModel):
    _name = 'mymodule.message.wizard'
    _description = "Show Message"

    message = fields.Text('Message', required=True)

#    @api.multi
    def action_close(self):
        return {'type': 'ir.actions.act_window_close'}
