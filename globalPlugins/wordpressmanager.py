# -*- coding: utf-8 -*-
# WordPress Manager Ultimate for NVDA
# Author: Volkan Ozdemir Software Services
# Website: https://www.volkan-ozdemir.com.tr
# Donation: https://www.paytr.com/link/N2IAQKm

import os
import sys
import threading
import globalPluginHandler
import ui
import webbrowser
import gui
import wx
import addonHandler
import config
import logHandler

# Initialize localization
addonHandler.initTranslation()

# Standard Library Injection
LIB_PATH = os.path.join(os.path.dirname(__file__), "lib")
if LIB_PATH not in sys.path:
	sys.path.insert(0, LIB_PATH)

try:
	import requests
except ImportError:
	requests = None

# Configuration Specification
confSpec = {
	"siteUrl": "string(default='')",
	"username": "string(default='')",
	"appPassword": "string(default='')",
}
config.conf.spec["wordpressManager"] = confSpec

class CreateContentDialog(gui.SettingsDialog):
	"""Ultimate dialog for creating Posts, Pages and selecting Categories."""
	title = _("WordPress: Create New Content")

	def makeSettings(self, settingsSizer):
		sHelper = gui.guiHelper.BoxSizerHelper(self, sizer=settingsSizer)
		
		self.postTitle = sHelper.addLabeledControl(_("Content &Title:"), wx.TextCtrl)
		self.postContent = sHelper.addLabeledControl(_("&Body Content:"), wx.TextCtrl, style=wx.TE_MULTILINE | wx.TE_RICH2)
		
		# Category Selection (Fetches dynamically in background)
		self.categoryList = sHelper.addLabeledControl(_("Select &Category:"), wx.CheckListBox, choices=[_("Loading categories...")])
		
		# Type and Status
		self.contentType = sHelper.addLabeledControl(_("Content &Type:"), wx.Choice, choices=[_("Post"), _("Page")])
		self.contentType.SetSelection(0)
		self.status = sHelper.addLabeledControl(_("&Status:"), wx.Choice, choices=[_("Draft"), _("Publish")])
		self.status.SetSelection(0)
		
		# Start fetching categories immediately
		threading.Thread(target=self.fetchCategories).start()

	def fetchCategories(self):
		if requests is None:
			wx.CallAfter(ui.message, _("Requests library not available. Please install dependencies."))
			return
		url = config.conf["wordpressManager"]["siteUrl"]
		auth = (config.conf["wordpressManager"]["username"], config.conf["wordpressManager"]["appPassword"])
		try:
			r = requests.get(f"{url}/wp-json/wp/v2/categories?per_page=100", auth=auth, timeout=10)
			if r.status_code == 200:
				self.categories = r.json()
				catNames = [cat['name'] for cat in self.categories]
				wx.CallAfter(self.updateCategoryList, catNames)
		except:
			wx.CallAfter(ui.message, _("Failed to load categories."))

	def updateCategoryList(self, names):
		self.categoryList.Clear()
		self.categoryList.AppendItems(names)

	def onOk(self, event):
		selected_cats = []
		if self.contentType.GetSelection() == 0: # Only for Posts
			for i in range(self.categoryList.GetCount()):
				if self.categoryList.IsChecked(i):
					selected_cats.append(self.categories[i]['id'])
		
		payload = {
			"title": self.postTitle.Value,
			"content": self.postContent.Value,
			"status": "publish" if self.status.GetSelection() == 1 else "draft",
			"categories": selected_cats if selected_cats else None
		}
		cType = "posts" if self.contentType.GetSelection() == 0 else "pages"
		threading.Thread(target=self.parentObject.api_call, args=("POST", cType, payload)).start()
		super(CreateContentDialog, self).onOk(event)

class WordPressSettingsDialog(gui.SettingsDialog):
	"""Settings dialog for WordPress Manager configuration."""
	title = _("WordPress Manager Settings")

	def makeSettings(self, settingsSizer):
		sHelper = gui.guiHelper.BoxSizerHelper(self, sizer=settingsSizer)
		
		self.siteUrl = sHelper.addLabeledControl(_("Site &URL:"), wx.TextCtrl)
		self.siteUrl.Value = config.conf["wordpressManager"]["siteUrl"]
		
		self.username = sHelper.addLabeledControl(_("&Username:"), wx.TextCtrl)
		self.username.Value = config.conf["wordpressManager"]["username"]
		
		self.appPassword = sHelper.addLabeledControl(_("&Application Password:"), wx.TextCtrl, style=wx.TE_PASSWORD)
		self.appPassword.Value = config.conf["wordpressManager"]["appPassword"]

	def onOk(self, event):
		config.conf["wordpressManager"]["siteUrl"] = self.siteUrl.Value
		config.conf["wordpressManager"]["username"] = self.username.Value
		config.conf["wordpressManager"]["appPassword"] = self.appPassword.Value
		super(WordPressSettingsDialog, self).onOk(event)

class CommentManagerDialog(gui.SettingsDialog):
	"""Manage recent comments: Approve, Spam, or Delete."""
	title = _("WordPress: Manage Comments")

	def makeSettings(self, settingsSizer):
		sHelper = gui.guiHelper.BoxSizerHelper(self, sizer=settingsSizer)
		self.commentList = sHelper.addLabeledControl(_("&Recent Comments:"), wx.ListBox, choices=[_("Fetching comments...")])
		
		# Action Buttons
		btnSizer = wx.BoxSizer(wx.HORIZONTAL)
		self.btnApprove = wx.Button(self, label=_("&Approve"))
		self.btnSpam = wx.Button(self, label=_("&Spam"))
		self.btnTrash = wx.Button(self, label=_("&Trash"))
		btnSizer.Add(self.btnApprove); btnSizer.Add(self.btnSpam); btnSizer.Add(self.btnTrash)
		settingsSizer.Add(btnSizer)
		
		self.btnApprove.Bind(wx.EVT_BUTTON, lambda e: self.onAction("approve"))
		self.btnSpam.Bind(wx.EVT_BUTTON, lambda e: self.onAction("spam"))
		self.btnTrash.Bind(wx.EVT_BUTTON, lambda e: self.onAction("trash"))
		
		threading.Thread(target=self.loadComments).start()

	def loadComments(self):
		if requests is None:
			wx.CallAfter(ui.message, _("Requests library not available. Please install dependencies."))
			return
		url = config.conf["wordpressManager"]["siteUrl"]
		auth = (config.conf["wordpressManager"]["username"], config.conf["wordpressManager"]["appPassword"])
		try:
			r = requests.get(f"{url}/wp-json/wp/v2/comments?per_page=10", auth=auth)
			self.comments = r.json()
			items = [f"{c['author_name']}: {c['content']['rendered'][:50]}" for c in self.comments]
			wx.CallAfter(self.commentList.Set, items)
		except: pass

	def onAction(self, action):
		idx = self.commentList.GetSelection()
		if idx == wx.NOT_FOUND: return
		c_id = self.comments[idx]['id']
		threading.Thread(target=self.parentObject.api_call, args=("POST", f"comments/{c_id}", {"status": action})).start()
		self.commentList.Delete(idx)

class GlobalPlugin(globalPluginHandler.GlobalPlugin):
	scriptCategory = _("WordPress Manager")

	def __init__(self):
		super(GlobalPlugin, self).__init__()
		self.createMenu()

	def createMenu(self):
		self.menu = gui.mainFrame.sysTrayIcon.menu
		self.wp_menu = wx.Menu()
		
		newItem = self.wp_menu.Append(wx.ID_ANY, _("New Content..."))
		gui.mainFrame.sysTrayIcon.Bind(wx.EVT_MENU, self.onNew, newItem)
		
		commentsItem = self.wp_menu.Append(wx.ID_ANY, _("Manage Comments..."))
		gui.mainFrame.sysTrayIcon.Bind(wx.EVT_MENU, self.onComments, commentsItem)
		
		self.wp_menu.AppendSeparator()
		settingsItem = self.wp_menu.Append(wx.ID_ANY, _("Settings..."))
		gui.mainFrame.sysTrayIcon.Bind(wx.EVT_MENU, self.onSettings, settingsItem)
		
		self.main_item = self.menu.AppendSubMenu(self.wp_menu, _("WordPress Manager"))

	def onNew(self, evt):
		d = CreateContentDialog(gui.mainFrame)
		d.parentObject = self
		d.Show()

	def onComments(self, evt):
		d = CommentManagerDialog(gui.mainFrame)
		d.parentObject = self
		d.Show()

	def onSettings(self, evt):
		WordPressSettingsDialog(gui.mainFrame).Show()

	def api_call(self, method, endpoint, data=None):
		if requests is None:
			wx.CallAfter(ui.message, _("Requests library not available. Please install dependencies."))
			return
		url = f"{config.conf['wordpressManager']['siteUrl']}/wp-json/wp/v2/{endpoint}"
		auth = (config.conf['wordpressManager']['username'], config.conf['wordpressManager']['appPassword'])
		try:
			if method == "POST":
				r = requests.post(url, auth=auth, json=data, timeout=15)
			else:
				r = requests.get(url, auth=auth, timeout=15)
			
			if r.status_code in [200, 201]:
				wx.CallAfter(ui.message, _("Operation successful."))
			else:
				wx.CallAfter(ui.message, _("Error: {code}").format(code=r.status_code))
		except:
			wx.CallAfter(ui.message, _("Connection failed."))

	def terminate(self):
		try: self.menu.Remove(self.main_item)
		except: pass