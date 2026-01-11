# -*- coding: utf-8 -*-
# WordPress Manager Ultimate for NVDA
# Version: 11.5
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

# Çeviri sistemini başlat
addonHandler.initTranslation()

# Kütüphane Yolu Enjeksiyonu
LIB_PATH = os.path.join(os.path.dirname(__file__), "lib")
if LIB_PATH not in sys.path:
	sys.path.insert(0, LIB_PATH)

try:
	import requests
except ImportError:
	requests = None

# Yapılandırma Tanımları
confSpec = {
	"siteUrl": "string(default='')",
	"username": "string(default='')",
	"appPassword": "string(default='')",
}
config.conf.spec["wordpressManager"] = confSpec

class WordPressSettingsDialog(gui.SettingsDialog):
	"""Bağlantı ayarlarının yapıldığı panel."""
	title = _("WordPress Manager Ayarları")

	def makeSettings(self, settingsSizer):
		sHelper = gui.guiHelper.BoxSizerHelper(self, sizer=settingsSizer)
		self.siteUrl = sHelper.addLabeledControl(_("Site &URL Adresi:"), wx.TextCtrl, value=config.conf["wordpressManager"]["siteUrl"])
		self.username = sHelper.addLabeledControl(_("&Kullanıcı Adı:"), wx.TextCtrl, value=config.conf["wordpressManager"]["username"])
		self.appPassword = sHelper.addLabeledControl(_("&Uygulama Parolası:"), wx.TextCtrl, value=config.conf["wordpressManager"]["appPassword"], style=wx.TE_PASSWORD)

	def onOk(self, event):
		config.conf["wordpressManager"]["siteUrl"] = self.siteUrl.Value.strip().rstrip('/')
		config.conf["wordpressManager"]["username"] = self.username.Value.strip()
		config.conf["wordpressManager"]["appPassword"] = self.appPassword.Value.strip()
		super(WordPressSettingsDialog, self).onOk(event)

class CreateContentDialog(gui.SettingsDialog):
	"""HTML destekli ve Enter sorunsuz içerik oluşturma diyaloğu."""
	title = _("WordPress: Yeni İçerik Oluştur")

	def makeSettings(self, settingsSizer):
		sHelper = gui.guiHelper.BoxSizerHelper(self, sizer=settingsSizer)
		self.postTitle = sHelper.addLabeledControl(_("İçerik &Başlığı:"), wx.TextCtrl)
		
		# HTML İsteğe bağlı onay kutusu
		self.useHtml = wx.CheckBox(self, label=_("HTML Desteğini Aktif Et"))
		settingsSizer.Add(self.useHtml)
		
		# Gövde Metni - TE_PROCESS_ENTER Enter'ı yakalamak için şart
		self.postContent = sHelper.addLabeledControl(
			_("&Gövde Metni:"), 
			wx.TextCtrl, 
			style=wx.TE_MULTILINE | wx.TE_RICH2 | wx.TE_PROCESS_ENTER
		)
		
		# Enter tuşuna basıldığında diyalog kapanmasın, alt satıra geçsin
		self.postContent.Bind(wx.EVT_TEXT_ENTER, self.onEnterPressed)
		
		self.categoryList = sHelper.addLabeledControl(_("&Kategori Seçin:"), wx.CheckListBox, choices=[_("Kategoriler yükleniyor...")])
		self.contentType = sHelper.addLabeledControl(_("İçerik &Türü:"), wx.Choice, choices=[_("Yazı"), _("Sayfa")])
		self.contentType.SetSelection(0)
		self.status = sHelper.addLabeledControl(_("&Durum:"), wx.Choice, choices=[_("Taslak"), _("Yayınla")])
		self.status.SetSelection(0)
		
		threading.Thread(target=self.fetchCategories).start()

	def onEnterPressed(self, event):
		"""Enter'a basıldığında imlecin olduğu yere alt satır karakteri ekler."""
		self.postContent.WriteText('\n')

	def fetchCategories(self):
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
			wx.CallAfter(ui.message, _("Kategoriler yüklenemedi."))

	def updateCategoryList(self, names):
		if not self: return
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
	"""Yorum yönetimi diyaloğu."""
	title = _("WordPress: Yorumları Yönet")

	def makeSettings(self, settingsSizer):
		sHelper = gui.guiHelper.BoxSizerHelper(self, sizer=settingsSizer)
		self.commentList = sHelper.addLabeledControl(_("&Son Yorumlar:"), wx.ListBox, choices=[_("Yorumlar alınıyor...")])
		
		btnSizer = wx.BoxSizer(wx.HORIZONTAL)
		self.btnApprove = wx.Button(self, label=_("&Onayla"))
		self.btnSpam = wx.Button(self, label=_("&Spam"))
		self.btnTrash = wx.Button(self, label=_("&Çöpe At"))
		
		btnSizer.Add(self.btnApprove); btnSizer.Add(self.btnSpam); btnSizer.Add(self.btnTrash)
		settingsSizer.Add(btnSizer)
		
		self.btnApprove.Bind(wx.EVT_BUTTON, lambda e: self.onAction("approve"))
		self.btnSpam.Bind(wx.EVT_BUTTON, lambda e: self.onAction("spam"))
		self.btnTrash.Bind(wx.EVT_BUTTON, lambda e: self.onAction("trash"))
		
		threading.Thread(target=self.loadComments).start()

	def loadComments(self):
		url = config.conf["wordpressManager"]["siteUrl"]
		auth = (config.conf["wordpressManager"]["username"], config.conf["wordpressManager"]["appPassword"])
		if not url: return
		try:
			r = requests.get(f"{url}/wp-json/wp/v2/comments?per_page=10", auth=auth)
			self.comments = r.json()
			items = [f"{c['author_name']}: {c['content']['rendered'][:50]}" for c in self.comments]
			wx.CallAfter(self.commentList.Set, items)
		except:
			pass

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
		
		itemNew = self.wpMenu.Append(wx.ID_ANY, _("Yeni İçerik..."))
		gui.mainFrame.sysTrayIcon.Bind(wx.EVT_MENU, self.onNew, itemNew)
		
		itemComm = self.wpMenu.Append(wx.ID_ANY, _("Yorumları Yönet..."))
		gui.mainFrame.sysTrayIcon.Bind(wx.EVT_MENU, self.onComments, itemComm)
		
		self.wpMenu.AppendSeparator()
		
		itemSet = self.wpMenu.Append(wx.ID_ANY, _("Ayarlar..."))
		gui.mainFrame.sysTrayIcon.Bind(wx.EVT_MENU, self.onSettings, itemSet)
		
		itemDonate = self.wpMenu.Append(wx.ID_ANY, _("Bağış Yapın (Geliştiriciyi Destekle)"))
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

	def apiCall(self, method, endpoint, data=None):
		if not config.conf['wordpressManager']['siteUrl']:
			wx.CallAfter(ui.message, _("Lütfen önce ayarları yapın."))
			return
		
		url = f"{config.conf['wordpressManager']['siteUrl']}/wp-json/wp/v2/{endpoint}"
		auth = (config.conf['wordpressManager']['username'], config.conf['wordpressManager']['appPassword'])
		
		try:
			if method == "POST":
				r = requests.post(url, auth=auth, json=data, timeout=15)
			else:
				r = requests.get(url, auth=auth, timeout=15)
			
			if r.status_code in [200, 201]:
				wx.CallAfter(ui.message, _("İşlem başarıyla tamamlandı."))
			else:
				wx.CallAfter(ui.message, _("Hata: {code}").format(code=r.status_code))
		except:
			wx.CallAfter(ui.message, _("Bağlantı kurulamadı. Ayarları kontrol edin."))

	def terminate(self):
		try:
			self.menu.Remove(self.mainItem)
		except:
			pass