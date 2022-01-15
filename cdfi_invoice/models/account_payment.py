# -*- coding: utf-8 -*-

import base64
import json
import requests
from lxml import etree
from odoo import api, fields, models, _
from odoo.exceptions import UserError, Warning
from . import amount_to_text_es_MX
from reportlab.graphics.barcode import createBarcodeDrawing
from reportlab.lib.units import mm
from datetime import date,datetime, timedelta
import pytz
from .tzlocal import get_localzone
from odoo import tools

class AccountPayment(models.Model):
    _inherit = 'account.payment'

    forma_pago = fields.Selection(selection=[('01', '01 - Efectivo'), 
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
                   ('31', '31 - Intermediario pagos'), ],
                                string=_('Forma de pago'), 
                            )
    tipo_comprobante = fields.Selection(
                                selection=[ ('P', 'Pago'),],
                                string=_('Tipo de comprobante'), default='P',
                            )
    methodo_pago = fields.Selection(
        selection=[('PUE', _('Pago en una sola exhibición')),
                   ('PPD', _('Pago en parcialidades o diferido')),],
        string=_('Método de pago'), 
    )
#    no_de_pago = fields.Integer("No. de pago", readonly=True)
    saldo_pendiente = fields.Float("Saldo pendiente", readonly=True)
    monto_pagar = fields.Float("Monto a pagar", compute='_compute_monto_pagar')
    saldo_restante = fields.Float("Saldo restante", readonly=True)
    fecha_pago = fields.Datetime("Fecha de pago")
    cuenta_emisor = fields.Many2one('res.partner.bank', string=_('Cuenta del emisor'))
    banco_emisor = fields.Char("Banco del emisor", related='cuenta_emisor.bank_name', readonly=True)
    rfc_banco_emisor = fields.Char(_("RFC banco emisor"), related='cuenta_emisor.bank_bic', readonly=True)
    numero_operacion = fields.Char(_("Número de operación"))
    banco_receptor = fields.Char(_("Banco receptor"), compute='_compute_banco_receptor')
    cuenta_beneficiario = fields.Char(_("Cuenta beneficiario"), compute='_compute_banco_receptor')
    rfc_banco_receptor = fields.Char(_("RFC banco receptor"), compute='_compute_banco_receptor')
    estado_pago = fields.Selection(
        selection=[('pago_no_enviado', 'REP no generado'), ('pago_correcto', 'REP correcto'), 
                   ('problemas_factura', 'Problemas con el pago'), ('solicitud_cancelar', 'Cancelación en proceso'),
                   ('cancelar_rechazo', 'Cancelación rechazada'), ('factura_cancelada', 'REP cancelado'), ],
        string=_('Estado CFDI'),
        default='pago_no_enviado',
        readonly=True
    )
    tipo_relacion = fields.Selection(
        selection=[('04', 'Sustitución de los CFDI previos'),],
        string=_('Tipo relación'),
    )
    uuid_relacionado = fields.Char(string=_('CFDI Relacionado'))
    confirmacion = fields.Char(string=_('Confirmación'))
    folio_fiscal = fields.Char(string=_('Folio Fiscal'), readonly=True)
    numero_cetificado = fields.Char(string=_('Numero de certificado'))
    cetificaso_sat = fields.Char(string=_('Cetificado SAT'))
    fecha_certificacion = fields.Char(string=_('Fecha y Hora Certificación'))
    cadena_origenal = fields.Char(string=_('Cadena Original del Complemento digital de SAT'))
    selo_digital_cdfi = fields.Char(string=_('Sello Digital del CDFI'))
    selo_sat = fields.Char(string=_('Sello del SAT'))
 #   moneda = fields.Char(string=_('Moneda'))
    monedap = fields.Char(string=_('Moneda'))
#    tipocambio = fields.Char(string=_('TipoCambio'))
    tipocambiop = fields.Char(string=_('TipoCambio'))
    folio = fields.Char(string=_('Folio'))
  #  version = fields.Char(string=_('Version'))
    number_folio = fields.Char(string=_('Folio'), compute='_get_number_folio')
    amount_to_text = fields.Char('Amount to Text', compute='_get_amount_to_text',
                                 size=256, 
                                 help='Amount of the invoice in letter')
    qr_value = fields.Char(string=_('QR Code Value'))
    qrcode_image = fields.Binary("QRCode")
#    rfc_emisor = fields.Char(string=_('RFC'))
#    name_emisor = fields.Char(string=_('Name'))
    xml_payment_link = fields.Char(string=_('XML link'), readonly=True)
    payment_mail_ids = fields.One2many('account.payment.mail', 'payment_id', string='Payment Mails')
    iddocumento = fields.Char(string=_('iddocumento'))
    fecha_emision = fields.Char(string=_('Fecha y Hora Certificación'))
    docto_relacionados = fields.Text("Docto relacionados",default='[]')
    cep_sello = fields.Char(string=_('cep_sello'))
    cep_numeroCertificado = fields.Char(string=_('cep_numeroCertificado'))
    cep_cadenaCDA = fields.Char(string=_('cep_cadenaCDA'))
    cep_claveSPEI = fields.Char(string=_('cep_claveSPEI'))
    
    @api.one
    @api.depends('name')
    def _get_number_folio(self):
        for record in self:
            if record.number:
                record.number_folio = record.name.replace('CUST.IN','').replace('/','')

    @api.model
    def get_docto_relacionados(self,payment):
        try:
            data = json.loads(payment.docto_relacionados)
        except Exception:
            data = []
        return data
    
    @api.multi
    def importar_incluir_cep(self):
        ctx = {'default_payment_id':self.id}
        return {
            'name': _('Importar factura de compra'),
            'view_type': 'form',
            'view_mode': 'form',
            'view_id': self.env.ref('cdfi_invoice.view_import_xml_payment_in_payment_form_view').id,
            'res_model': 'import.account.payment.from.xml',
            'context': ctx,
            'type': 'ir.actions.act_window',
            'target': 'new',
        }
        
    @api.onchange('journal_id')
    def _onchange_journal(self):
        if self.journal_id:
            self.currency_id = self.journal_id.currency_id or self.company_id.currency_id
            # Set default payment method (we consider the first to be the default one)
            payment_methods = self.payment_type == 'inbound' and self.journal_id.inbound_payment_method_ids or self.journal_id.outbound_payment_method_ids
            self.payment_method_id = payment_methods and payment_methods[0] or False
            # Set payment method domain (restrict to methods enabled for the journal and to selected payment type)
            payment_type = self.payment_type in ('outbound', 'transfer') and 'outbound' or 'inbound'
            self.forma_pago = self.journal_id.forma_pago
            return {'domain': {'payment_method_id': [('payment_type', '=', payment_type), ('id', 'in', payment_methods.ids)]}}
        return {}
    
    @api.onchange('payment_date')
    def _onchange_payment_date(self):
        if self.payment_date:
            self.fecha_pago = datetime.combine((self.payment_date), datetime.max.time())

    @api.multi
    def add_resitual_amounts(self):
        if self.invoice_ids and self.docto_relacionados != '[]':
            for invoice in self.invoice_ids:
                data = json.loads(self.docto_relacionados) or []
                for line in data:
                    if invoice.folio_fiscal == line.get('IdDocumento',False):
                        monto_restante = invoice.residual
                        monto_pagar_docto = float(line.get('ImpSaldoAnt',False)) - monto_restante
                        line['ImpPagado'] = monto_pagar_docto
                        line['ImpSaldoInsoluto'] = monto_restante
                        self.write({'docto_relacionados': json.dumps(data)})
        elif self.reconciled_invoice_ids or self.invoice_ids and self.docto_relacionados == '[]':
               docto_relacionados = []
               monto_pagado_asignar = round(self.monto_pagar,2)
               for invoice in self.reconciled_invoice_ids:
                    #_logger.info('entra2 02 %s', invoice.number)
                    if invoice.factura_cfdi:
                        #revisa la cantidad que se va a pagar en el docuemnto
                        if self.currency_id.name != invoice.moneda:
                            if self.currency_id.name == 'MXN':
                                tipocambiop = round(invoice.currency_id.with_context(date=self.payment_date).rate,6) + 0.000001
                            else:
                                tipocambiop = float(invoice.tipocambio)/float(self.currency_id.with_context(date=self.payment_date).rate)
                        else:
                            tipocambiop = invoice.tipocambio
                        payment_dict = json.loads(invoice.payments_widget)
                        payment_content = payment_dict['content']
                        monto_pagado = 0
                        for invoice_payments in payment_content:
                            if invoice_payments['account_payment_id'] == self.id:
                                monto_pagado = invoice_payments['amount']
                        docto_relacionados.append({
                              'moneda': invoice.moneda,
                              'tipodecambio': tipocambiop,
                              'methodo_pago': invoice.methodo_pago,
                              'iddocumento': invoice.folio_fiscal,
                              'folio_facura': invoice.number_folio,
                              'no_de_pago': len(payment_content), 
                              'saldo_pendiente': round(invoice.residual + monto_pagado,2),
                              'monto_pagar': monto_pagado,
                              'saldo_restante': invoice.residual,
                        })
               saldo_pendiente_total = sum(inv.residual for inv in self.invoice_ids)
               self.write({'docto_relacionados': json.dumps(docto_relacionados),
                           'saldo_pendiente': saldo_pendiente_total, 'saldo_restante':saldo_pendiente_total - monto_pagado_asignar})
         #   else: # si tieen información
          #         _logger.info('entra2 04 %s', self.docto_relacionados)

    @api.model
    def create(self, vals):
        res = super(AccountPayment, self).create(vals)
        if res.invoice_ids:
            docto_relacionados = []
            monto_pagado_asignar = round(res.monto_pagar,2)
            for invoice in res.invoice_ids:
                if invoice.factura_cfdi:
                    #revisa la cantidad que se va a pagar en el docuemnto
                    if res.currency_id.name != invoice.moneda:
                        if res.currency_id.name == 'MXN':
                            tipocambiop = self.set_decimals(round(invoice.currency_id.with_context(date=res.date).rate,6) + 0.000001, self.currency_id.no_decimales_tc)
                        else:
                            tipocambiop = self.set_decimals(float(invoice.tipocambio)/float(res.currency_id.with_context(date=res.date).rate), self.currency_id.no_decimales_tc)
                    else:
                        tipocambiop = '1' #invoice.tipocambio
                    docto_relacionados.append({
                          'MonedaDR': invoice.moneda,
                          'EquivalenciaDR': tipocambiop,
                       #   'MetodoDePagoDR': invoice.methodo_pago,
                          'IdDocumento': invoice.folio_fiscal,
                          'folio_facura': invoice.number_folio,
                          'NumParcialidad': len(invoice.payment_ids.filtered(lambda x: x.state not in ['cancelled', 'draft']))+1, 
                          'ImpSaldoAnt': self.set_decimals(invoice.residual, self.currency_id.no_decimales),
                          'ImpPagado': 0,
                          'ImpSaldoInsoluto': 0,
                          'ObjetoImpDR': '01', # conseguir este dato y agregar nodos de traslado
                    })
            saldo_pendiente_total = sum(inv.residual for inv in res.invoice_ids)
            res.write({'docto_relacionados': json.dumps(docto_relacionados),
                       'saldo_pendiente': saldo_pendiente_total, 'saldo_restante':saldo_pendiente_total - monto_pagado_asignar})
        return res
    @api.multi
    def post(self):
        res = super(AccountPayment, self).post()
        for rec in self:
            rec.add_resitual_amounts()
            rec._onchange_payment_date()
            rec._onchange_journal()
        return res

    @api.one
    @api.depends('amount')
    def _compute_monto_pagar(self):
        for record in self:
            if record.amount:
                record.monto_pagar = record.amount
            else:
                record.monto_pagar = 0

    @api.one
    @api.depends('journal_id')
    def _compute_banco_receptor(self):
        if self.journal_id and self.journal_id.bank_id:
            self.banco_receptor = self.journal_id.bank_id.name
            self.rfc_banco_receptor = self.journal_id.bank_id.bic
        if self.journal_id:
            self.cuenta_beneficiario = self.journal_id.bank_acc_number

    @api.one
    @api.depends('amount', 'currency_id')
    def _get_amount_to_text(self):
        for record in self:
            record.amount_to_text = amount_to_text_es_MX.get_amount_to_text(record, record.amount_total, 'es_cheque', record.currency_id.name)
        
    @api.model
    def _get_amount_2_text(self, amount_total):
        return amount_to_text_es_MX.get_amount_to_text(self, amount_total, 'es_cheque', self.currency_id.name)
            
    @api.model
    def to_json(self):
        if not self.company_id.archivo_cer:
            raise UserError(_('El archivo del certificado .cer no se encuentra.'))
        if not self.company_id.archivo_key:
            raise UserError(_('El archivo del certificado .key no se encuentra.'))
        if not self.company_id.contrasena:
            raise UserError(_('La contraseña del certificado no se encuentra.'))

        archivo_cer = self.company_id.archivo_cer
        archivo_key = self.company_id.archivo_key

        no_decimales = self.currency_id.no_decimales
        no_decimales_tc = self.currency_id.no_decimales_tc

        self.monedap = self.currency_id.name
        if self.currency_id.name == 'MXN':
            self.tipocambiop = '1'
        else:
            self.tipocambiop = self.set_decimals(self.currency_id.with_context(date=self.date).rate, no_decimales_tc)

        timezone = self._context.get('tz')
        if not timezone:
            timezone = self.env.user.partner_id.tz or 'America/Mexico_City'
        #timezone = tools.ustr(timezone).encode('utf-8')

        if not self.fecha_pago:
            raise Warning("Falta configurar fecha de pago en la sección de CFDI del documento.")
        else:
            local = pytz.timezone(timezone)
            naive_from = self.fecha_pago
            local_dt_from = naive_from.replace(tzinfo=pytz.UTC).astimezone(local)
            date_from = local_dt_from.strftime ("%Y-%m-%dT%H:%M:%S")
        self.add_resitual_amounts()

        #corregir hora
        local2 = pytz.timezone(timezone)
        naive_from2 = datetime.now() 
        local_dt_from2 = naive_from2.replace(tzinfo=pytz.UTC).astimezone(local2)
        date_payment = local_dt_from2.strftime ("%Y-%m-%dT%H:%M:%S")

        self.check_cfdi_values()

        if self.partner_id.rfc == 'XAXX010101000':
            nombre = 'PUBLICO GENERAL'
        else:
            nombre = self.clean_text(self.partner_id.name.upper())

        conceptos = []
        conceptos.append({
                          'ClaveProdServ': '84111506',
                          'ClaveUnidad': 'ACT',
                          'cantidad': 1,
                          'descripcion': 'Pago',
                          'valorunitario': '0',
                          'importe': '0',
                          'ObjetoImp': '01',
                    })

        pagos = []
        pagos.append({
                      'FechaPago': date_from,
                      'FormaDePagoP': self.forma_pago,
                      'MonedaP': self.monedap,
                      'TipoCambioP': self.tipocambiop if self.monedap != 'MXN' else '1',
                      'Monto':  self.set_decimals(self.amount, no_decimales),
                      'NumOperacion': self.numero_operacion,

                      'RfcEmisorCtaOrd': False, #self.rfc_banco_emisor,
                      'NomBancoOrdExt': self.banco_emisor,
                      'CtaOrdenante': self.cuenta_emisor and self.cuenta_emisor.acc_number or '',
                      'RfcEmisorCtaBen': False, #self.rfc_banco_receptor,
                      'CtaBeneficiario': False, #self.cuenta_beneficiario,
                      'DoctoRelacionado': json.loads(self.docto_relacionados),
                    })

        if self.reconciled_invoice_ids:
            request_params = {
                'factura': {
                      'serie': self.company_id.serie_complemento,
                      'folio': self.name.replace('CUST.IN','').replace('/',''),
                      'fecha_expedicion': date_payment,
                      'subtotal': '0',
                      'moneda': 'XXX',
                      'total': '0',
                      'tipocomprobante': 'P',
                      'LugarExpedicion': self.journal_id.codigo_postal or self.company_id.zip,
                      'confirmacion': self.confirmacion,
                      'Exportacion': '01',
                },
                'emisor': {
                      'rfc': self.company_id.rfc.upper(),
                      'nombre': self.clean_text(self.company_id.nombre_fiscal.upper()),
                      'RegimenFiscal': self.company_id.regimen_fiscal,
                },
                'receptor': {
                      'nombre': nombre,
                      'rfc': self.partner_id.rfc.upper(),
                      'ResidenciaFiscal': self.partner_id.residencia_fiscal,
                      'NumRegIdTrib': self.partner_id.registro_tributario,
                      'UsoCFDI': 'CP01',
                      'RegimenFiscalReceptor': self.partner_id.regimen_fiscal,
                      'DomicilioFiscalReceptor': self.partner_id.zip,
                },

                'informacion': {
                      'cfdi': '4.0',
                      'sistema': 'odoo12',
                      'version': '6',
                      'api_key': self.company_id.proveedor_timbrado,
                      'modo_prueba': self.company_id.modo_prueba,
                },

                'conceptos': conceptos,

                'totales': {'MontoTotalPagos': self.set_decimals(self.amount, no_decimales)},

                'pagos20': {'Pagos': pagos},

                'certificados': {
                      'archivo_cer': archivo_cer.decode("utf-8"),
                      'archivo_key': archivo_key.decode("utf-8"),
                      'contrasena': self.company_id.contrasena,
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

        else:
            raise Warning("No tiene ninguna factura ligada al documento de pago, debe al menos tener una factura ligada. \n Desde la factura crea el pago para que se asocie la factura al pago.")
        return request_params

    def check_cfdi_values(self):
        if not self.company_id.rfc:
            raise UserError(_('El emisor no tiene RFC configurado.'))
        if not self.company_id.name:
            raise UserError(_('El emisor no tiene nombre configurado.'))
        if not self.partner_id.rfc:
            raise UserError(_('El receptor no tiene RFC configurado.'))
        if not self.company_id.regimen_fiscal:
            raise UserError(_('El emisor no régimen fiscal configurado.'))
        if not self.journal_id.codigo_postal and not self.company_id.zip:
            raise UserError(_('El emisor no tiene código postal configurado.'))
        if not self.forma_pago:
            raise UserError(_('Falta configurar la forma de pago.'))

    def set_decimals(self, amount, precision):
        if amount is None or amount is False:
            return None
        return '%.*f' % (precision, amount)

    def clean_text(self, text):
        clean_text = text.replace('\n', ' ').replace('\\', ' ').replace('-', ' ').replace('/', ' ').replace('|', ' ')
        clean_text = clean_text.replace(',', ' ').replace(';', ' ').replace('>', ' ').replace('<', ' ')
        return clean_text[:1000]

    @api.multi
    def complete_payment(self):
        for p in self:
            if p.folio_fiscal:
                 p.write({'estado_pago': 'pago_correcto'})
                 return True

            values = p.to_json()
            if self.company_id.proveedor_timbrado == 'multifactura':
                url = '%s' % ('http://facturacion.itadmin.com.mx/api/payment')
            elif self.company_id.proveedor_timbrado == 'multifactura2':
                url = '%s' % ('http://facturacion2.itadmin.com.mx/api/payment')
            elif self.company_id.proveedor_timbrado == 'multifactura3':
                url = '%s' % ('http://facturacion3.itadmin.com.mx/api/payment')
            elif self.company_id.proveedor_timbrado == 'gecoerp':
                if self.company_id.modo_prueba:
                    #url = '%s' % ('https://ws.gecoerp.com/itadmin/pruebas/payment/?handler=OdooHandler33')
                    url = '%s' % ('https://itadmin.gecoerp.com/payment2/?handler=OdooHandler33')
                else:
                    url = '%s' % ('https://itadmin.gecoerp.com/payment2/?handler=OdooHandler33')
            try:
                response = requests.post(url , 
                                     auth=None,verify=False, data=json.dumps(values), 
                                     headers={"Content-type": "application/json"})
            except Exception as e:
                error = str(e)
                if "Name or service not known" in error or "Failed to establish a new connection" in error:
                     raise Warning("Servidor fuera de servicio, favor de intentar mas tarde")
                else:
                     raise Warning(error)

            if "Whoops, looks like something went wrong." in response.text:
                raise Warning("Error con el servidor de facturación, favor de reportar el error a su persona de soporte. \nNo intente timbrar de nuevo hasta validar que el servicio ha sido restablecido, ya que pudiera timbrar doble alguna factura.")
            else:
                json_response = response.json()
            xml_file_link = False
            estado_pago = json_response['estado_pago']
            if estado_pago == 'problemas_pago':
                raise UserError(_(json_response['problemas_message']))
            # Receive and stroe XML 
            if json_response.get('pago_xml'):
                xml_file_link = p.company_id.factura_dir + '/' + p.name.replace('/', '_') + '.xml'
                xml_file = open(xml_file_link, 'w')
                xml_payment = base64.b64decode(json_response['pago_xml'])
                xml_file.write(xml_payment.decode("utf-8"))
                xml_file.close()
                p._set_data_from_xml(xml_payment)
                    
                xml_file_name = p.name.replace('/', '_') + '.xml'
                self.env['ir.attachment'].sudo().create(
                                            {
                                                'name': xml_file_name,
                                                'datas': json_response['pago_xml'],
                                                'datas_fname': xml_file_name,
                                                'res_model': self._name,
                                                'res_id': p.id,
                                                'type': 'binary'
                                            })
                report = self.env['ir.actions.report']._get_report_from_name('cdfi_invoice.report_payment')
                report_data = report.render_qweb_pdf([p.id])[0]
                pdf_file_name = p.name.replace('/', '_') + '.pdf'
                self.env['ir.attachment'].sudo().create(
                                            {
                                                'name': pdf_file_name,
                                                'datas': base64.b64encode(report_data),
                                                'datas_fname': pdf_file_name,
                                                'res_model': self._name,
                                                'res_id': p.id,
                                                'type': 'binary'
                                            })

            p.write({'estado_pago': estado_pago,
                    'xml_payment_link': xml_file_link})
            p.message_post(body="CFDI emitido")
            
    @api.multi
    def validate_complete_payment(self):
        self.post()
        return {
            'name': _('Payments'),
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'account.payment',
            'view_id': False,
            'type': 'ir.actions.act_window',
            'res_id': self.id,
        }

    @api.one
    def _set_data_from_xml(self, xml_payment):
        if not xml_payment:
            return None
        NSMAP = {
                 'xsi':'http://www.w3.org/2001/XMLSchema-instance',
                 'cfdi':'http://www.sat.gob.mx/cfd/4', 
                 'tfd': 'http://www.sat.gob.mx/TimbreFiscalDigital',
                 'pago20': 'http://www.sat.gob.mx/Pagos20',
                 }
        xml_data = etree.fromstring(xml_payment)
        Complemento = xml_data.findall('cfdi:Complemento', NSMAP)

        for complementos in Complemento:
            TimbreFiscalDigital = complementos.find('tfd:TimbreFiscalDigital', NSMAP)
            if TimbreFiscalDigital:
                break

        self.numero_cetificado = xml_data.attrib['NoCertificado']
        self.fecha_emision = xml_data.attrib['Fecha']
        self.cetificaso_sat = TimbreFiscalDigital.attrib['NoCertificadoSAT']
        self.fecha_certificacion = TimbreFiscalDigital.attrib['FechaTimbrado']
        self.selo_digital_cdfi = TimbreFiscalDigital.attrib['SelloCFD']
        self.selo_sat = TimbreFiscalDigital.attrib['SelloSAT']
        self.folio_fiscal = TimbreFiscalDigital.attrib['UUID']
        self.folio = xml_data.attrib['Folio']     
        self.invoice_datetime = xml_data.attrib['Fecha']
        version = TimbreFiscalDigital.attrib['Version']
        self.cadena_origenal = '||%s|%s|%s|%s|%s||' % (version, self.folio_fiscal, self.fecha_certificacion, 
                                                         self.selo_digital_cdfi, self.cetificaso_sat)
        
        options = {'width': 275 * mm, 'height': 275 * mm}
        amount_str = str(self.amount).split('.')
        qr_value = 'https://verificacfdi.facturaelectronica.sat.gob.mx/default.aspx?&id=%s&re=%s&rr=%s&tt=%s.%s&fe=%s' % (self.folio_fiscal,
                                                 self.company_id.rfc, 
                                                 self.partner_id.rfc,
                                                 amount_str[0].zfill(10),
                                                 amount_str[1].ljust(6, '0'),
                                                 self.selo_digital_cdfi[-8:],
                                                 )
        self.qr_value = qr_value
        ret_val = createBarcodeDrawing('QR', value=qr_value, **options)
        self.qrcode_image = base64.encodestring(ret_val.asString('jpg'))
        #self.folio_fiscal = TimbreFiscalDigital.attrib['UUID']

    @api.multi
    def send_payment(self):
        self.ensure_one()
        template = self.env.ref('cdfi_invoice.email_template_payment', False)
        compose_form = self.env.ref('mail.email_compose_message_wizard_form', False)
            
        ctx = dict()
        ctx.update({
            'default_model': 'account.payment',
            'default_res_id': self.id,
            'default_use_template': bool(template),
            'default_template_id': template.id,
            'default_composition_mode': 'comment',
        })
        return {
            'name': _('Compose Email'),
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'mail.compose.message',
            'views': [(compose_form.id, 'form')],
            'view_id': compose_form.id,
            'target': 'new',
            'context': ctx,
        }

    @api.multi
    def action_cfdi_cancel(self):
        for p in self:
            #if invoice.factura_cfdi:
                if p.estado_pago == 'factura_cancelada':
                    pass
                    # raise UserError(_('La factura ya fue cancelada, no puede volver a cancelarse.'))
                if not p.company_id.archivo_cer:
                    raise UserError(_('Falta la ruta del archivo .cer'))
                if not p.company_id.archivo_key:
                    raise UserError(_('Falta la ruta del archivo .key'))
                archivo_cer = p.company_id.archivo_cer.decode("utf-8")
                archivo_key = p.company_id.archivo_key.decode("utf-8")
                archivo_xml_link = p.company_id.factura_dir + '/' + p.name.replace('/', '_') + '.xml'
                with open(archivo_xml_link, 'rb') as cf:
                     archivo_xml = base64.b64encode(cf.read())
                values = {
                          'rfc': p.company_id.rfc,
                          'api_key': p.company_id.proveedor_timbrado,
                          'uuid': p.folio_fiscal,
                          'folio': p.folio,
                          'serie_factura': p.company_id.serie_complemento,
                          'modo_prueba': p.company_id.modo_prueba,
                            'certificados': {
                                  'archivo_cer': archivo_cer,
                                  'archivo_key': archivo_key,
                                  'contrasena': p.company_id.contrasena,
                            },
                          'xml': archivo_xml.decode("utf-8"),
                          'motivo': self.env.context.get('motivo_cancelacion',False),
                          'foliosustitucion': self.env.context.get('foliosustitucion',''),
                          }
                if p.company_id.proveedor_timbrado == 'multifactura':
                    url = '%s' % ('http://facturacion.itadmin.com.mx/api/refund')
                elif p.company_id.proveedor_timbrado == 'multifactura2':
                    url = '%s' % ('http://facturacion2.itadmin.com.mx/api/refund')
                elif p.company_id.proveedor_timbrado == 'multifactura3':
                    url = '%s' % ('http://facturacion3.itadmin.com.mx/api/refund')
                elif p.company_id.proveedor_timbrado == 'gecoerp':
                    if p.company_id.modo_prueba:
                         #url = '%s' % ('https://ws.gecoerp.com/itadmin/pruebas/refund/?handler=OdooHandler33')
                        url = '%s' % ('https://itadmin.gecoerp.com/refund/?handler=OdooHandler33')
                    else:
                        url = '%s' % ('https://itadmin.gecoerp.com/refund/?handler=OdooHandler33')
                response = requests.post(url , 
                                         auth=None,verify=False, data=json.dumps(values), 
                                         headers={"Content-type": "application/json"})

                json_response = response.json()
                
                if json_response['estado_factura'] == 'problemas_factura':
                    raise UserError(_(json_response['problemas_message']))
                elif json_response.get('factura_xml', False):
                    if p.name:
                        xml_file_link = p.company_id.factura_dir + '/CANCEL_' + p.name.replace('/', '_') + '.xml'
                    else:
                        xml_file_link = p.company_id.factura_dir + '/CANCEL_' + p.folio + '.xml'
                    xml_file = open(xml_file_link, 'w')
                    xml_invoice = base64.b64decode(json_response['factura_xml'])
                    xml_file.write(xml_invoice.decode("utf-8"))
                    xml_file.close()
                    if p.name:
                        file_name = p.name.replace('/', '_') + '.xml'
                    else:
                        file_name = p.folio + '.xml'
                    self.env['ir.attachment'].sudo().create(
                                                {
                                                    'name': file_name,
                                                    'datas': json_response['factura_xml'],
                                                    'datas_fname': file_name,
                                                    'res_model': self._name,
                                                    'res_id': p.id,
                                                    'type': 'binary'
                                                })
                p.write({'estado_pago': json_response['estado_factura']})
                p.message_post(body="CFDI Cancelado")

class AccountPaymentMail(models.Model):
    _name = "account.payment.mail"
    _inherit = ['mail.thread']
    _description = "Payment Mail"
    
    payment_id = fields.Many2one('account.payment', string='Payment')
    name = fields.Char(related='payment_id.name')
    xml_payment_link = fields.Char(related='payment_id.xml_payment_link')
    partner_id = fields.Many2one(related='payment_id.partner_id')
    company_id = fields.Many2one(related='payment_id.company_id')
    
class MailTemplate(models.Model):
    "Templates for sending email"
    _inherit = 'mail.template'
    
    @api.model
    def _get_file(self, url):
        url = url.encode('utf8')
        filename, headers = urllib.urlretrieve(url)
        fn, file_extension = os.path.splitext(filename)
        return  filename, file_extension.replace('.', '')

    @api.multi
    def generate_email(self, res_ids, fields=None):
        results = super(MailTemplate, self).generate_email(res_ids, fields=fields)
        
        if isinstance(res_ids, (int)):
            res_ids = [res_ids]
        res_ids_to_templates = super(MailTemplate, self).get_email_template(res_ids)

        # templates: res_id -> template; template -> res_ids
        templates_to_res_ids = {}
        for res_id, template in res_ids_to_templates.items():
            templates_to_res_ids.setdefault(template, []).append(res_id)
        
        template_id = self.env.ref('cdfi_invoice.email_template_payment')
        for template, template_res_ids in templates_to_res_ids.items():
            if template.id  == template_id.id:
                for res_id in template_res_ids:
                    payment = self.env[template.model].browse(res_id)
                    if payment.xml_payment_link:
                        attachments =  results[res_id]['attachments'] or []
                        names = payment.xml_payment_link.split('/')
                        fn = names[len(names) - 1]
                        data = open(payment.xml_payment_link, 'rb').read()
                        attachments.append((fn, base64.b64encode(data)))
                        results[res_id]['attachments'] = attachments
        return results

class AccountPaymentTerm(models.Model):
    "Terminos de pago"
    _inherit = "account.payment.term"

    methodo_pago = fields.Selection(
        selection=[('PUE', _('Pago en una sola exhibición')),
                   ('PPD', _('Pago en parcialidades o diferido')),],
        string=_('Método de pago'), 
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
