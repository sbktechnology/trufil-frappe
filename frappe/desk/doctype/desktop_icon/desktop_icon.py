# -*- coding: utf-8 -*-
# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

import frappe
import json
import random
from frappe.model.document import Document
from frappe import _

class DesktopIcon(Document):
	def validate(self):
		if not self.label:
			self.label = self.module_name

	def on_trash(self):
		clear_desktop_icons_cache()

def after_doctype_insert():
	frappe.db.add_unique('Desktop Icon', ('module_name', 'owner', 'standard'))

def get_desktop_icons(user=None):
	'''Return desktop icons for user'''
	if not user:
		user = frappe.session.user

	user_icons = frappe.cache().hget('desktop_icons', user)

	if not user_icons:
		fields = ['module_name', 'hidden', 'label', 'link', 'type', 'icon', 'color',
			'_doctype', 'idx', 'force_show', 'reverse', 'custom', 'standard']

		standard_icons = frappe.db.get_all('Desktop Icon',
			fields=fields, filters={'standard': 1})

		standard_map = {}
		for icon in standard_icons:
			standard_map[icon.module_name] = icon

		user_icons = frappe.db.get_all('Desktop Icon', fields=fields,
			filters={'standard': 0, 'owner': user})


		# update hidden property
		for icon in user_icons:
			standard_icon = standard_map.get(icon.module_name, None)

			# override properties from standard icon
			if standard_icon:
				for key in ('route', 'label', 'color', 'icon', 'link'):
					if standard_icon.get(key):
						icon[key] = standard_icon.get(key)

				if standard_icon.hidden:
					icon.hidden = 1

					# flag for modules_setup page
					icon.hidden_in_standard = 1

				elif standard_icon.force_show:
					icon.hidden = 0

		# add missing standard icons (added via new install apps?)
		user_icon_names = [icon.module_name for icon in user_icons]
		for standard_icon in standard_icons:
			if standard_icon.module_name not in user_icon_names:

				# flag for modules_setup page
				standard_icon.hidden_in_standard = standard_icon.hidden

				user_icons.append(standard_icon)

		user_blocked_modules = frappe.get_doc('User', user).get_blocked_modules()
		for icon in user_icons:
			if icon.module_name in user_blocked_modules:
				icon.hidden = 1

		# sort by idx
		user_icons.sort(lambda a, b: 1 if a.idx > b.idx else -1)

		frappe.cache().hset('desktop_icons', user, user_icons)

	return user_icons

@frappe.whitelist()
def add_user_icon(label, link, type, _doctype):
	'''Add a new user desktop icon to the desktop'''
	icon_name = frappe.db.exists('Desktop Icon', {'standard': 0, 'link': link, 'owner': frappe.session.user})
	if icon_name and frappe.db.get_value('Desktop Icon', icon_name, 'hidden'):
		frappe.db.set_value('Desktop Icon', icon_name, 'hidden', 0)
		clear_desktop_icons_cache()

	elif not icon_name:
		idx = frappe.db.sql('select max(idx) from `tabDesktop Icon` where owner=%s',
			frappe.session.user)[0][0] or \
			frappe.db.sql('select count(*) from `tabDesktop Icon` where standard=1')[0][0]

		module = frappe.db.get_value('DocType', _doctype, 'module')
		module_icon = frappe.get_value('Desktop Icon', {'standard':1, 'module_name':module},
			['icon', 'color', 'reverse'], as_dict=True)

		if not module_icon:
			module_icon = frappe._dict()
			opts = random.choice(palette)
			module_icon.color = opts[0]
			module_icon.reverse = 0 if (len(opts) > 1) else 1

		try:
			frappe.get_doc({
				'doctype': 'Desktop Icon',
				'label': label,
				'module_name': label,
				'link': link,
				'type': type,
				'_doctype': _doctype,
				'icon': module_icon.icon,
				'color': module_icon.color,
				'reverse': module_icon.reverse,
				'idx': idx + 1,
				'custom': 1,
				'standard': 0
			}).insert(ignore_permissions=True)
			clear_desktop_icons_cache()

			frappe.msgprint(_('Added'))

		except Exception, e:
			raise e
	else:
		frappe.msgprint(_('Already on desktop'))

@frappe.whitelist()
def set_order(new_order):
	'''set new order by duplicating user icons'''
	if isinstance(new_order, basestring):
		new_order = json.loads(new_order)
	for i, module_name in enumerate(new_order):
		if module_name not in ('Explore',):
			icon = get_user_copy(module_name, frappe.session.user)
			icon.db_set('idx', i)

	clear_desktop_icons_cache()

def set_hidden_list(hidden_list, user=None):
	'''Sets property `hidden`=1 in **Desktop Icon** for given user.
	If user is None then it will set global values.
	It will also set the rest of the icons as shown (`hidden` = 0)'''
	if isinstance(hidden_list, basestring):
		hidden_list = json.loads(hidden_list)

	# set as hidden
	for module_name in hidden_list:
		set_hidden(module_name, user, 1)

	# set as seen
	for module_name in list(set(get_all_icons()) - set(hidden_list)):
		set_hidden(module_name, user, 0)

	if user:
		clear_desktop_icons_cache()
	else:
		frappe.clear_cache()

def set_hidden(module_name, user=None, hidden=1):
	'''Set module hidden property for given user. If user is not specified,
		hide/unhide it globally'''
	if user:
		icon = get_user_copy(module_name, user)
	else:
		icon = frappe.get_doc('Desktop Icon', {'standard': 1, 'module_name': module_name})

	if hidden and icon.custom:
		frappe.delete_doc(icon.doctype, icon.name, ignore_permissions=True)
		return

	icon.db_set('hidden', hidden)

def get_all_icons():
	return [d.module_name for d in frappe.get_all('Desktop Icon',
		filters={'standard': 1}, fields=['module_name'])]

def clear_desktop_icons_cache(user=None):
	frappe.cache().hdel('desktop_icons', user or frappe.session.user)
	frappe.cache().hdel('bootinfo', user or frappe.session.user)

def get_user_copy(module_name, user=None):
	'''Return user copy (Desktop Icon) of the given module_name. If user copy does not exist, create one.

	:param module_name: Name of the module
	:param user: User for which the copy is required (optional)
	'''
	if not user:
		user = frappe.session.user

	desktop_icon_name = frappe.db.get_value('Desktop Icon',
		{'module_name': module_name, 'owner': user, 'standard': 0})

	if desktop_icon_name:
		return frappe.get_doc('Desktop Icon', desktop_icon_name)
	else:
		return make_user_copy(module_name, user)

def make_user_copy(module_name, user):
	'''Insert and return the user copy of a standard Desktop Icon'''
	standard_name = frappe.db.get_value('Desktop Icon', {'module_name': module_name, 'standard': 1})

	if not standard_name:
		frappe.throw('{0} not found'.format(module_name), frappe.DoesNotExistError)

	original = frappe.get_doc('Desktop Icon', standard_name)

	desktop_icon = frappe.get_doc({
		'doctype': 'Desktop Icon',
		'standard': 0,
		'owner': user,
		'module_name': module_name
	})

	for key in ('app', 'label', 'route', 'type', '_doctype', 'idx', 'reverse', 'force_show'):
		if original.get(key):
			desktop_icon.set(key, original.get(key))

	desktop_icon.insert(ignore_permissions=True)

	return desktop_icon

def sync_desktop_icons():
	'''Sync desktop icons from all apps'''
	for app in frappe.get_installed_apps():
		sync_from_app(app)

def sync_from_app(app):
	'''Sync desktop icons from app. To be called during install'''
	try:
		modules = frappe.get_attr(app + '.config.desktop.get_data')() or {}
	except ImportError:
		return []

	if isinstance(modules, dict):
		modules_list = []
		for m, desktop_icon in modules.iteritems():
			desktop_icon['module_name'] = m
			modules_list.append(desktop_icon)
	else:
		modules_list = modules

	for i, m in enumerate(modules_list):
		desktop_icon_name = frappe.db.get_value('Desktop Icon',
			{'module_name': m['module_name'], 'app': app, 'standard': 1})
		if desktop_icon_name:
			desktop_icon = frappe.get_doc('Desktop Icon', desktop_icon_name)
		else:
			# new icon
			desktop_icon = frappe.get_doc({
				'doctype': 'Desktop Icon',
				'idx': i,
				'standard': 1,
				'app': app,
				'owner': 'Administrator'
			})

		if 'doctype' in m:
			m['_doctype'] = m.pop('doctype')

		desktop_icon.update(m)
		desktop_icon.save()

	return modules_list

palette = (
	('#FFC4C4',),
	('#FFE8CD',),
	('#FFD2C2',),
	('#FF8989',),
	('#FFD19C',),
	('#FFA685',),
	('#FF4D4D', 1),
	('#FFB868',),
	('#FF7846', 1),
	('#A83333', 1),
	('#A87945', 1),
	('#A84F2E', 1),
	('#D2D2FF',),
	('#F8D4F8',),
	('#DAC7FF',),
	('#A3A3FF',),
	('#F3AAF0',),
	('#B592FF',),
	('#7575FF', 1),
	('#EC7DEA', 1),
	('#8E58FF', 1),
	('#4D4DA8', 1),
	('#934F92', 1),
	('#5E3AA8', 1),
	('#EBF8CC',),
	('#FFD7D7',),
	('#D2F8ED',),
	('#D9F399',),
	('#FFB1B1',),
	('#A4F3DD',),
	('#C5EC63',),
	('#FF8989', 1),
	('#77ECCA',),
	('#7B933D', 1),
	('#A85B5B', 1),
	('#49937E', 1),
	('#FFFACD',),
	('#D2F1FF',),
	('#CEF6D1',),
	('#FFF69C',),
	('#A6E4FF',),
	('#9DECA2',),
	('#FFF168',),
	('#78D6FF',),
	('#6BE273',),
	('#A89F45', 1),
	('#4F8EA8', 1),
	('#428B46', 1)
)
