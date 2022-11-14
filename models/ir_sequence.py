# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models, api, _
from odoo.exceptions import ValidationError, UserError

DYNAMIC_PREFIX_DELIMITER = '%'
DYNAMIC_PREFIX_START_VAR = '('
DYNAMIC_PREFIX_END_VAR = ')'
DYNAMIC_PREFIX_STATIC_VALUE_DELIMITER = '**'


class IrSequence(models.Model):
    _inherit = 'ir.sequence'

    sequence_type = fields.Selection([('sequence', 'Sequence'),
                                      ('sequence_template', 'Sequence template')], required=True, default='sequence')
    related_model = fields.Many2one('ir.model', string='Model using this sequence',
                                    help="This will help to control the dynamic prefix field before its usage "
                                         "(as no hard relation existing between object and sequence,with this data the system will be able to compare "
                                         "the fields put in the dynamic part with the controls existing on this Model)")
    dynamic_prefix_code = fields.Text(string='Dynamic prefix codification',
                                      help='Please take in account all this constraints specified under <Legend for dynamic prefix>')
    parent_id = fields.Many2one('ir.sequence', string='Parent sequence',
                                help='The sequence model that create this sequence')
    child_ids = fields.Many2many('ir.sequence', compute='_compute_child_ids')
    child_count = fields.Integer(compute='_compute_child_count')

    # FIXME: this method must be removed from here
    @api.model
    def _translate_dynamic_values(self, src):
        domain = [('src', '=', src), ('lang','=', self.env.context.get('lang'))]
        return self.env['ir.translation'].search(domain, limit=1).value or src

    @api.depends('child_ids')
    def _compute_child_count(self):
        self.child_count = len(self.child_ids)

    def _compute_child_ids(self):
        domain = [('parent_id', '=', self.id)]
        self.child_ids = self.search(domain).ids

    def action_view_child_sequences(self):
        return self._get_action_view_sequences(self.child_ids)

    def _get_action_view_sequences(self, sequences):
        action = self.env["ir.actions.actions"]._for_xml_id("base.ir_sequence_form")

        if len(sequences) > 1:
            action['domain'] = [('id', 'in', sequences.ids)]
        elif sequences:
            form_view = [(self.env.ref('base.sequence_view').id, 'form')]
            if 'views' in action:
                action['views'] = form_view + [(state, view) for state, view in action['views'] if view != 'form']
            else:
                action['views'] = form_view
            action['res_id'] = sequences.id
        # Prepare the context.
        action['context'] = dict(self._context, default_parent_id=self.id)
        return action

    @api.constrains('sequence_type', 'related_model', 'dynamic_prefix_code')
    def _check_dynamic_prefix_code(self):
        if self.sequence_type == 'sequence_template' and self.related_model:
            self._check_dynamic_prefix_code_syntax(self.dynamic_prefix_code, self.related_model.model)

    @api.model
    def _check_dynamic_prefix_code_syntax(self, dynamic_prefix_code, model_name):
        valid_syntax = dynamic_prefix_code.count(DYNAMIC_PREFIX_DELIMITER) == 1 and dynamic_prefix_code.count(
            DYNAMIC_PREFIX_START_VAR) == 1 \
                       and dynamic_prefix_code.count(DYNAMIC_PREFIX_END_VAR) == 1
        assert valid_syntax, _(
            'Invalid syntax for the dynamic prefix,please check the rules in Legend for dynamic prefix')
        fields = self._parse_fields_for_check(dynamic_prefix_code)
        for field in fields:
            try:
                getattr(self.env[model_name], field)
            except AttributeError as e:
                raise ValidationError(_('No field %s detected in model %s') % (
                field, self._translate_dynamic_values(self.env[model_name]._description)))

    @api.model
    def _parse_fields_for_check(self, dynamic_prefix_code):
        fields_list = self._parse_fields(dynamic_prefix_code, remove_static_fields=True)
        # for the check purpose we need only the first field not the nested one
        return [field.split(".")[0] for field in fields_list]

    @api.model
    def _parse_fields(self, dynamic_prefix_code, remove_static_fields=False):
        field_list = self._parse_dynamic_prefix_variable(dynamic_prefix_code)
        if not remove_static_fields:
            return field_list
        field_list = [field for field in field_list if field not in self._parse_static_fields(dynamic_prefix_code)]
        return field_list

    @api.model
    def _parse_static_fields(self, dynamic_prefix_code):
        field_list = self._parse_dynamic_prefix_variable(dynamic_prefix_code)
        return [field for field in field_list if field.startswith(DYNAMIC_PREFIX_STATIC_VALUE_DELIMITER)]

    @api.model
    def _parse_static_field(self, field):
        return field.replace(DYNAMIC_PREFIX_STATIC_VALUE_DELIMITER, '')

    @api.model
    def _parse_dynamic_prefix_variable(self, dynamic_prefix_code):
        fields_str = dynamic_prefix_code.replace(DYNAMIC_PREFIX_DELIMITER, '').replace(DYNAMIC_PREFIX_START_VAR, '') \
            .replace(DYNAMIC_PREFIX_END_VAR, '')
        return fields_str.split(',')

    @api.model
    def next_by_code(self, sequence_code, sequence_date=None):
        """ Inherit this method to request the template sequence if this is the case."""
        company_id = self.env.company.id
        seq_ids = self.search([('code', '=', sequence_code), ('company_id', 'in', [company_id, False])],
                              order='company_id,sequence_type DESC')
        if not seq_ids:
            return super(IrSequence, self).next_by_code(sequence_code, sequence_date=sequence_date)
        seq = seq_ids[0]
        if seq.sequence_type == 'sequence':
            return super(IrSequence, self).next_by_code(sequence_code, sequence_date=sequence_date)
        return seq._next_by_sequence_template(sequence_code, sequence_date=sequence_date)

    def next_by_id(self, sequence_date=None):
        """ Inherit this method to request the template sequence if this is the case."""
        self.check_access_rights('read')
        if self.sequence_type == 'sequence':
            return super(IrSequence, self).next_by_id(sequence_date=sequence_date)
        return self._next_by_sequence_template(None, sequence_date=sequence_date)

    def _next_by_sequence_template(self, sequence_code=None, sequence_date=None):
        company_id = self.env.company.id
        prefix = self._build_prefix()
        domain = [('prefix', '=', prefix), ('company_id', 'in', [company_id, False])]
        if sequence_code:
            domain.append(('code', '=', sequence_code))
        seq_ids = self.search(domain, order='company_id')
        if not seq_ids:
            seq_ids |= self._create_sequence_from_template(prefix)
        seq_id = seq_ids[0]
        return seq_id._next(sequence_date=sequence_date)

    def _create_sequence_from_template(self, prefix):
        new_sequence = self.copy({'prefix': prefix,
                                  'parent_id': self.id,
                                  'sequence_type': 'sequence',
                                  'number_next': 1,
                                  'related_model': False,
                                  'dynamic_prefix_code': False,
                                  })
        # we have to copy the date range if the template have that
        if self.use_date_range and self.date_range_ids:
            for date_range in self.date_range_ids:
                new_date_range = date_range.copy({
                    'sequence_id': new_sequence.id,
                    'number_next_actual': date_range.number_next_actual
                })
        return new_sequence

    def _build_prefix(self):
        dynamic_prefix_fields = self.env.context.get('dynamic_prefix_fields', False)
        if not dynamic_prefix_fields:
            raise UserError(_("No dynamic prefix fields has been found!"))
        record = self.env[self.related_model.model]
        fields = self._parse_fields(self.dynamic_prefix_code)
        prefix = ''
        for field in fields:
            if field in self._parse_static_fields(self.dynamic_prefix_code):
                prefix += self._parse_static_field(field)
                continue
            try:
                # get only the field name in the case of many2one field (not all the chain)
                field_obj = record._fields[field.split(".")[0]]
            except KeyError as ae:
                raise UserError(_('No field %s detected in model %s') % (field, record._name))
            else:
                if field_obj.type not in ('char', 'many2one'):
                    raise UserError(
                        _('field used in dynamic prefix must be char or many2one,the type of field %s is %s') % (
                            field_obj.string, field_obj.type))
                if field_obj.type == 'char':
                    val = dynamic_prefix_fields[field_obj.name]
                    if not val:
                        raise UserError(_("No value found for %s,can't generate dynamic prefix!") % (field_obj.name))
                    prefix += val
                elif field_obj.type == 'many2one':
                    prefix += self._parse_many2one_field(record, dynamic_prefix_fields, field)
        return prefix

    def _remove_static_fields(self):
        pass

    @api.model
    def _parse_many2one_field(self, record, dynamic_prefix_fields, field):
        prefix = ''
        nested_list_fields = field.split(".")
        next_field = nested_list_fields.pop(0)
        record_obj = self.env[record._fields[next_field].comodel_name]
        record = record_obj.browse(dynamic_prefix_fields[next_field])
        if not record:
            raise UserError(_("No value found for %s,can't generate dynamic prefix!") % (next_field))
        while nested_list_fields:
            next_field = nested_list_fields.pop(0)
            val = getattr(record, next_field)
            if not val:
                raise UserError(_("No value found for %s,can't generate dynamic prefix!") % (next_field))
            if isinstance(val, str):
                prefix += val
            else:
                record = val
        return prefix
