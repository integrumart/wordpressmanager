# -*- coding: utf-8 -*-
# WordPress Manager Ultimate for NVDA
# Version: 19.0
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

# Configuration
confSpec = {
	"siteUrl": "string(default='')",
	"username": "string(default='')",
	"appPassword": "string(default='')",
}
config.conf.spec["wordpressManager"] = confSpec

class WordPressSettingsDialog(gui.SettingsDialog):
	title = _("WordPress Manager Settings")

	def makeSettings(self, settingsSizer):
		sHelper = gui.guiHelper.BoxSizerHelper(self, sizer=settingsSizer)
		self.siteUrl = sHelper.addLabeledControl(_("Site &URL:"), wx.TextCtrl, value=config.conf["wordpressManager"]["siteUrl"])
		self.username = sHelper.addLabeledControl(_("&Username:"), wx.TextCtrl, value=config.conf["wordpressManager"]["username"])
		self.appPassword = sHelper.addLabeledControl(_("&App Password:"), wx.TextCtrl, value=config.conf["wordpressManager"]["appPassword"], style=wx.TE_PASSWORD)

	def onOk(self, event):
		url = self.siteUrl.Value.strip().rstrip('/')
		if url and not url.startswith("https://"):
			if not gui.messageBox(_("Insecure connection (HTTP) detected. Continue?"), _("Security Warning"), wx.YES_NO | wx.ICON_WARNING) == wx.YES:
				return
		config.conf["wordpressManager"]["siteUrl"] = url
		config.conf["wordpressManager"]["username"] = self.username.Value.strip()
		config.conf["wordpressManager"]["appPassword"] = self.appPassword.Value.strip()
		super(WordPressSettingsDialog, self).onOk(event)

class SiteSettingsDialog(gui.SettingsDialog):
	title = _("WordPress: Site Administration")

	def makeSettings(self, settingsSizer):
		sHelper = gui.guiHelper.BoxSizerHelper(self, sizer=settingsSizer)
		self.siteTitle = sHelper.addLabeledControl(_("Site &Title:"), wx.TextCtrl)
		self.siteDescription = sHelper.addLabeledControl(_("&Tagline:"), wx.TextCtrl)
		self.postsPerPage = sHelper.addLabeledControl(_("&Posts Per Page:"), wx.SpinCtrl, min=1, max=100)
		self.defaultCategory = sHelper.addLabeledControl(_("Default &Category ID:"), wx.TextCtrl)
		threading.Thread(target=self.loadSettings).start()

	def loadSettings(self):
		url = f"{config.conf['wordpressManager']['siteUrl']}/wp-json/wp/v2/settings"
		auth = (config.conf['wordpressManager']['username'], config.conf['wordpressManager']['appPassword'])
		try:
			r = requests.get(url, auth=auth, timeout=10)
			if r.status_code == 200:
				data = r.json()
				wx.CallAfter(self.siteTitle.SetValue, str(data.get('title', '')))
				wx.CallAfter(self.siteDescription.SetValue, str(data.get('description', '')))
				wx.CallAfter(self.postsPerPage.SetValue, int(data.get('posts_per_page', 10)))
				wx.CallAfter(self.defaultCategory.SetValue, str(data.get('default_category', '1')))
		except: pass

	def onOk(self, event):
		payload = {
			"title": self.siteTitle.Value,
			"description": self.siteDescription.Value,
			"posts_per_page": self.postsPerPage.Value,
			"default_category": int(self.defaultCategory.Value)
		}
		threading.Thread(target=self.parentObject.apiCall, args=("POST", "settings", payload)).start()
		super(SiteSettingsDialog, self).onOk(event)

class CreateContentDialog(gui.SettingsDialog):
	title = _("WordPress: Create Content")

	def makeSettings(self, settingsSizer):
		sHelper = gui.guiHelper.BoxSizerHelper(self, sizer=settingsSizer)
		self.postTitle = sHelper.addLabeledControl(_("&Title:"), wx.TextCtrl)
		self.useHtml = wx.CheckBox(self, label=_("Enable HTML"))
		settingsSizer.Add(self.useHtml)
		self.postContent = sHelper.addLabeledControl(_("&Content:"), wx.TextCtrl, style=wx.TE_MULTILINE | wx.TE_RICH2 | wx.TE_PROCESS_ENTER)
		self.postContent.Bind(wx.EVT_TEXT_ENTER, lambda e: self.postContent.WriteText('\n'))
		self.postTags = sHelper.addLabeledControl(_("&Tags (IDs):"), wx.TextCtrl)
		self.visibility = sHelper.addLabeledControl(_("&Visibility:"), wx.Choice, choices=[_("Public"), _("Private")])
		self.postPassword = sHelper.addLabeledControl(_("&Password:"), wx.TextCtrl)
		self.categoryList = sHelper.addLabeledControl(_("&Categories:"), wx.CheckListBox, choices=[_("Loading...")])
		self.contentType = sHelper.addLabeledControl(_("T&ype:"), wx.Choice, choices=[_("Post"), _("Page")])
		self.status = sHelper.addLabeledControl(_("&Status:"), wx.Choice, choices=[_("Draft"), _("Publish")])
		threading.Thread(target=self.fetchCategories).start()

	def fetchCategories(self):
		url = config.conf["wordpressManager"]["siteUrl"]
		auth = (config.conf["wordpressManager"]["username"], config.conf["wordpressManager"]["appPassword"])
		try:
			r = requests.get(f"{url}/wp-json/wp/v2/categories", auth=auth, timeout=10)
			if r.status_code == 200:
				self.categories = r.json()
				wx.CallAfter(self.categoryList.Set, [c['name'] for c in self.categories])
		except: pass

	def onOk(self, event):
		selectedCats = [self.categories[i]['id'] for i in range(self.categoryList.Count) if self.categoryList.IsChecked(i)]
		payload = {
			"title": self.postTitle.Value,
			"content": self.postContent.Value,
			"status": "publish" if self.status.Selection == 1 else "draft",
			"password": self.postPassword.Value.strip(),
			"categories": selectedCats
		}
		if self.visibility.Selection == 1: payload["status"] = "private"
		if self.postTags.Value: 
			try: payload["tags"] = [int(t.strip()) for t in self.postTags.Value.split(',')]
			except: pass
		
		cType = "posts" if self.contentType.Selection == 0 else "pages"
		threading.Thread(target=self.parentObject.apiCall, args=("POST", cType, payload)).start()
		super(CreateContentDialog, self).onOk(event)

class CommentManagerDialog(gui.SettingsDialog):
	title = _("WordPress: Manage Comments")

	def makeSettings(self, settingsSizer):
		sHelper = gui.guiHelper.BoxSizerHelper(self, sizer=settingsSizer)
		self.commentList = sHelper.addLabeledControl(_("&Recent Comments:"), wx.ListBox, choices=[_("Loading...")])
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
		url = config.conf["wordpressManager"]["siteUrl"]
		auth = (config.conf["wordpressManager"]["username"], config.conf["wordpressManager"]["appPassword"])
		try:
			r = requests.get(f"{url}/wp-json/wp/v2/comments?per_page=10", auth=auth)
			if r.status_code == 200:
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

	def createMenu(self):
		self.menu = gui.mainFrame.sysTrayIcon.menu
		self.wpMenu = wx.Menu()
		itemNew = self.wpMenu.Append(wx.ID_ANY, _("New Content..."))
		gui.mainFrame.sysTrayIcon.Bind(wx.EVT_MENU, self.onNew, itemNew)
		itemComm = self.wpMenu.Append(wx.ID_ANY, _("Manage Comments..."))
		gui.mainFrame.sysTrayIcon.Bind(wx.EVT_MENU, self.onComments, itemComm)
		itemSiteSet = self.wpMenu.Append(wx.ID_ANY, _("Site Settings..."))
		gui.mainFrame.sysTrayIcon.Bind(wx.EVT_MENU, self.onSiteSettings, itemSiteSet)
		self.wpMenu.AppendSeparator()
		itemAccSet = self.wpMenu.Append(wx.ID_ANY, _("Account Configuration..."))
		gui.mainFrame.sysTrayIcon.Bind(wx.EVT_MENU, self.onSettings, itemAccSet)
		itemWeb = self.wpMenu.Append(wx.ID_ANY, _("Visit Website"))
		gui.mainFrame.sysTrayIcon.Bind(wx.EVT_MENU, self.onWeb, itemWeb)
		itemDonate = self.wpMenu.Append(wx.ID_ANY, _("Donate (Support Developer)"))
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

	def onSiteSettings(self, evt):
		d = SiteSettingsDialog(gui.mainFrame)
		d.parentObject = self
		d.Show()

	def onSettings(self, evt):
		WordPressSettingsDialog(gui.mainFrame).Show()

	def onWeb(self, evt):
		webbrowser.open("https://www.volkan-ozdemir.com.tr")

	def onDonate(self, evt):
		webbrowser.open("https://www.paytr.com/link/N2IAQKm")

	def apiCall(self, method, endpoint, data=None):
		if not config.conf['wordpressManager']['siteUrl']:
			wx.CallAfter(ui.message, _("Configuration required."))
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
				wx.CallAfter(ui.message, _("Error code: {code}").format(code=r.status_code))
		except:
			wx.CallAfter(ui.message, _("Connection failed."))

	def terminate(self):
		try: self.menu.Remove(self.mainItem)
		except: pass