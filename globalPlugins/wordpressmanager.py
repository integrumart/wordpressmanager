# -*- coding: utf-8 -*-
# WordPress Manager Ultimate for NVDA
# Version: 8.9
# Author: Volkan Ozdemir Software Services

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

# Initialize translation
addonHandler.initTranslation()

# Library Path Injection
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

class WordPressSettingsDialog(gui.SettingsDialog):
	"""Panel where WordPress connection settings are made."""
	title = _("WordPress Manager Settings") # English source

	def makeSettings(self, settingsSizer):
		sHelper = gui.guiHelper.BoxSizerHelper(self, sizer=settingsSizer)
		self.siteUrl = sHelper.addLabeledControl(_("Site &URL Address:"), wx.TextCtrl, value=config.conf["wordpressManager"]["siteUrl"])
		self.username = sHelper.addLabeledControl(_("&Username:"), wx.TextCtrl, value=config.conf["wordpressManager"]["username"])
		self.appPassword = sHelper.addLabeledControl(_("&Application Password:"), wx.TextCtrl, value=config.conf["wordpressManager"]["appPassword"], style=wx.TE_PASSWORD)

	def onOk(self, event):
		config.conf["wordpressManager"]["siteUrl"] = self.siteUrl.Value.strip().rstrip('/')
		config.conf["wordpressManager"]["username"] = self.username.Value.strip()
		config.conf["wordpressManager"]["appPassword"] = self.appPassword.Value.strip()
		super(WordPressSettingsDialog, self).onOk(event)

class CreateContentDialog(gui.SettingsDialog):
	"""Content creation dialog."""
	title = _("WordPress: Create New Content")

	def makeSettings(self, settingsSizer):
		sHelper = gui.guiHelper.BoxSizerHelper(self, sizer=settingsSizer)
		self.postTitle = sHelper.addLabeledControl(_("Content &Title:"), wx.TextCtrl)
		self.postContent = sHelper.addLabeledControl(_("&Body Text:"), wx.TextCtrl, style=wx.TE_MULTILINE | wx.TE_RICH2)
		self.categoryList = sHelper.addLabeledControl(_("Select &Category:"), wx.CheckListBox, choices=[_("Loading categories...")])
		self.contentType = sHelper.addLabeledControl(_("Content &Type:"), wx.Choice, choices=[_("Post"), _("Page")])
		self.contentType.SetSelection(0)
		self.status = sHelper.addLabeledControl(_("&Status:"), wx.Choice, choices=[_("Draft"), _("Publish")])
		self.status.SetSelection(0)
		threading.Thread(target=self.fetchCategories).start()

	def fetchCategories(self): # camelCase
		url = config.conf["wordpressManager"]["siteUrl"]
		auth = (config.conf["wordpressManager"]["username"], config.conf["wordpressManager"]["appPassword"])
		if not url: return
		try:
			r = requests.get(f"{url}/wp-json/wp/v2/categories?per_page=100", auth=auth, timeout=10)
			if r.status_code == 200:
				self.categories = r.json()
				catNames = [cat['name'] for cat in self.categories]
				wx.CallAfter(self.updateCategoryList, catNames)
		except:
			wx.CallAfter(ui.message, _("Could not load categories."))

	def updateCategoryList(self, names): # camelCase
		self.categoryList.Clear()
		self.categoryList.AppendItems(names)

	def onOk(self, event):
		selectedCats = []
		if self.contentType.GetSelection() == 0:
			for i in range(self.categoryList.GetCount()):
				if self.categoryList.IsChecked(i):
					selectedCats.append(self.categories[i]['id'])
		payload = {
			"title": self.postTitle.Value,
			"content": self.postContent.Value,
			"status": "publish" if self.status.GetSelection() == 1 else "draft"
		}
		if selectedCats:
			payload["categories"] = selectedCats
		cType = "posts" if self.contentType.GetSelection() == 0 else "pages"
		threading.Thread(target=self.parentObject.apiCall, args=("POST", cType, payload)).start()
		super(CreateContentDialog, self).onOk(event)

class CommentManagerDialog(gui.SettingsDialog):
	"""Comment management dialog."""
	title = _("WordPress: Manage Comments")

	def makeSettings(self, settingsSizer):
		sHelper = gui.guiHelper.BoxSizerHelper(self, sizer=settingsSizer)
		self.commentList = sHelper.addLabeledControl(_("&Recent Comments:"), wx.ListBox, choices=[_("Fetching comments...")])
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

	def loadComments(self): # camelCase
		url = config.conf["wordpressManager"]["siteUrl"]
		auth = (config.conf["wordpressManager"]["username"], config.conf["wordpressManager"]["appPassword"])
		if not url: return
		try:
			r = requests.get(f"{url}/wp-json/wp/v2/comments?per_page=10", auth=auth)
			self.comments = r.json()
			items = [f"{c['author_name']}: {c['content']['rendered'][:50]}" for c in self.comments]
			wx.CallAfter(self.commentList.Set, items)
		except: pass

	def onAction(self, action):
		idx = self.commentList.GetSelection()
		if idx == wx.NOT_FOUND: return
		cId = self.comments[idx]['id']
		threading.Thread(target=self.parentObject.apiCall, args=("POST", f"comments/{cId}", {"status": action})).start()
		self.commentList.Delete(idx)

class GlobalPlugin(globalPluginHandler.GlobalPlugin):
	scriptCategory = _("WordPress Manager")

	def __init__(self):
		super(GlobalPlugin, self).__init__()
		self.createMenu()

	def createMenu(self): # camelCase
		self.menu = gui.mainFrame.sysTrayIcon.menu
		self.wpMenu = wx.Menu() # PascalCase menu
		itemNew = self.wpMenu.Append(wx.ID_ANY, _("New Content..."))
		gui.mainFrame.sysTrayIcon.Bind(wx.EVT_MENU, self.onNew, itemNew)
		itemComm = self.wpMenu.Append(wx.ID_ANY, _("Manage Comments..."))
		gui.mainFrame.sysTrayIcon.Bind(wx.EVT_MENU, self.onComments, itemComm)
		self.wpMenu.AppendSeparator()
		itemSet = self.wpMenu.Append(wx.ID_ANY, _("Settings..."))
		gui.mainFrame.sysTrayIcon.Bind(wx.EVT_MENU, self.onSettings, itemSet)
		itemDonate = self.wpMenu.Append(wx.ID_ANY, _("Support the Developer (Donation)"))
		gui.mainFrame.sysTrayIcon.Bind(wx.EVT_MENU, self.onDonate, itemDonate)
		self.mainItem = self.menu.AppendSubMenu(self.wpMenu, _("WordPress Manager"))

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

	def onDonate(self, evt):
		webbrowser.open("https://www.paytr.com/link/N2IAQKm")

	def apiCall(self, method, endpoint, data=None): # camelCase
		if not config.conf['wordpressManager']['siteUrl']:
			wx.CallAfter(ui.message, _("Please configure the settings first."))
			return
		url = f"{config.conf['wordpressManager']['siteUrl']}/wp-json/wp/v2/{endpoint}"
		auth = (config.conf['wordpressManager']['username'], config.conf['wordpressManager']['appPassword'])
		try:
			if method == "POST":
				r = requests.post(url, auth=auth, json=data, timeout=15)
			else:
				r = requests.get(url, auth=auth, timeout=15)
			if r.status_code in [200, 201]:
				wx.CallAfter(ui.message, _("Action completed successfully."))
			else:
				wx.CallAfter(ui.message, _("Error: {code}").format(code=r.status_code))
		except:
			wx.CallAfter(ui.message, _("Connection failed. Please check your settings."))

	def terminate(self):
		try: self.menu.Remove(self.mainItem)
		except: pass