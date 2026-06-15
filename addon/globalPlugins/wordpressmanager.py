# -*- coding: utf-8 -*-
# WordPress Manager Ultimate for NVDA
# Version: 20.0
# Author: Volkan Ozdemir Software Services, Fauzan, S.Kom.

import os
import sys
import threading
import urllib.request
import urllib.parse
import urllib.error
import json
import base64
import mimetypes
import globalPluginHandler
import ui
import webbrowser
import gui
import wx
import addonHandler
import config
import api

# Initialize translation
addonHandler.initTranslation()

def _make_request(url, auth=None, method="GET", data=None, timeout=15):
	headers = {}
	if auth and len(auth) == 2 and auth[0]:
		auth_str = f"{auth[0]}:{auth[1]}"
		encoded_auth = base64.b64encode(auth_str.encode('utf-8')).decode('ascii')
		headers['Authorization'] = f"Basic {encoded_auth}"
	
	req_data = None
	if data is not None:
		req_data = json.dumps(data).encode('utf-8')
		headers['Content-Type'] = 'application/json'
		
	try:
		# In urllib.request, specifying data automatically changes the method to POST if method is not set.
		req = urllib.request.Request(url, data=req_data, headers=headers, method=method)
		with urllib.request.urlopen(req, timeout=timeout) as response:
			return response.getcode(), json.loads(response.read().decode('utf-8'))
	except urllib.error.HTTPError as e:
		try:
			return e.code, json.loads(e.read().decode('utf-8'))
		except:
			return e.code, None
	except Exception:
		return 0, None

# Configuration
confSpec = {
	"siteUrl": "string(default='')",
	"username": "string(default='')",
	"appPassword": "string(default='')",
	"savedSites": "string(default='[]')"
}
config.conf.spec["wordpressManager"] = confSpec

class WordPressSettingsDialog(gui.SettingsDialog):
	title = _("WordPress Manager Settings")

	def makeSettings(self, settingsSizer):
		sHelper = gui.guiHelper.BoxSizerHelper(self, sizer=settingsSizer)
		
		# Profile Selector
		self.savedSitesStr = config.conf["wordpressManager"]["savedSites"]
		try:
			self.savedSites = json.loads(self.savedSitesStr)
			if not isinstance(self.savedSites, list): self.savedSites = []
		except:
			self.savedSites = []
			
		profileNames = [site.get("name", site.get("url", "Unknown")) for site in self.savedSites]
		self.profileChoice = sHelper.addLabeledControl(_("Saved &Profiles:"), wx.Choice, choices=profileNames)
		self.profileChoice.Bind(wx.EVT_CHOICE, self.onProfileSelect)
		
		btnSizer = wx.BoxSizer(wx.HORIZONTAL)
		self.btnSaveProfile = wx.Button(self, label=_("&Save Profile"))
		self.btnDelProfile = wx.Button(self, label=_("&Delete Profile"))
		self.btnSaveProfile.Bind(wx.EVT_BUTTON, self.onSaveProfile)
		self.btnDelProfile.Bind(wx.EVT_BUTTON, self.onDeleteProfile)
		btnSizer.Add(self.btnSaveProfile)
		btnSizer.Add(self.btnDelProfile)
		settingsSizer.Add(btnSizer)
		
		self.siteUrl = sHelper.addLabeledControl(_("Site &URL:"), wx.TextCtrl, value=config.conf["wordpressManager"]["siteUrl"])
		self.username = sHelper.addLabeledControl(_("&Username:"), wx.TextCtrl, value=config.conf["wordpressManager"]["username"])
		self.appPassword = sHelper.addLabeledControl(_("&App Password:"), wx.TextCtrl, value=config.conf["wordpressManager"]["appPassword"], style=wx.TE_PASSWORD)

	def onProfileSelect(self, evt):
		idx = self.profileChoice.GetSelection()
		if idx != wx.NOT_FOUND and idx < len(self.savedSites):
			site = self.savedSites[idx]
			self.siteUrl.SetValue(site.get("url", ""))
			self.username.SetValue(site.get("username", ""))
			self.appPassword.SetValue(site.get("appPassword", ""))

	def onSaveProfile(self, evt):
		with wx.TextEntryDialog(self, _("Enter a name for this profile:"), _("Save Profile")) as dlg:
			if dlg.ShowModal() == wx.ID_OK:
				name = dlg.GetValue().strip()
				if not name: return
				
				found = False
				for site in self.savedSites:
					if site.get("name") == name:
						site["url"] = self.siteUrl.Value.strip().rstrip('/')
						site["username"] = self.username.Value.strip()
						site["appPassword"] = self.appPassword.Value.strip()
						found = True
						break
				if not found:
					self.savedSites.append({
						"name": name,
						"url": self.siteUrl.Value.strip().rstrip('/'),
						"username": self.username.Value.strip(),
						"appPassword": self.appPassword.Value.strip()
					})
					self.profileChoice.Append(name)
					self.profileChoice.SetSelection(self.profileChoice.GetCount() - 1)
				
				config.conf["wordpressManager"]["savedSites"] = json.dumps(self.savedSites)
				wx.CallAfter(ui.message, _("Profile saved."))

	def onDeleteProfile(self, evt):
		idx = self.profileChoice.GetSelection()
		if idx != wx.NOT_FOUND:
			del self.savedSites[idx]
			self.profileChoice.Delete(idx)
			config.conf["wordpressManager"]["savedSites"] = json.dumps(self.savedSites)
			wx.CallAfter(ui.message, _("Profile deleted."))

	def onOk(self, event):
		url = self.siteUrl.Value.strip().rstrip('/')
		if url and not url.startswith("https://"):
			if not gui.messageBox(_("Insecure connection (HTTP) detected. Continue?"), _("Security Warning"), wx.YES_NO | wx.ICON_WARNING) == wx.YES:
				return
		config.conf["wordpressManager"]["siteUrl"] = url
		config.conf["wordpressManager"]["username"] = self.username.Value.strip()
		config.conf["wordpressManager"]["appPassword"] = self.appPassword.Value.strip()
		config.conf["wordpressManager"]["savedSites"] = json.dumps(self.savedSites)
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
		status, data = _make_request(url, auth=auth, timeout=10)
		if status == 200 and data:
			wx.CallAfter(self.siteTitle.SetValue, str(data.get('title', '')))
			wx.CallAfter(self.siteDescription.SetValue, str(data.get('description', '')))
			wx.CallAfter(self.postsPerPage.SetValue, int(data.get('posts_per_page', 10)))
			wx.CallAfter(self.defaultCategory.SetValue, str(data.get('default_category', '1')))

	def onOk(self, event):
		try: default_cat = int(self.defaultCategory.Value)
		except ValueError: default_cat = 1
		payload = {
			"title": self.siteTitle.Value,
			"description": self.siteDescription.Value,
			"posts_per_page": self.postsPerPage.Value,
			"default_category": default_cat
		}
		threading.Thread(target=self.parentObject.apiCall, args=("POST", "settings", payload)).start()
		super(SiteSettingsDialog, self).onOk(event)

class CreateContentDialog(gui.SettingsDialog):
	title = _("WordPress: Create Content")

	def __init__(self, parent, postData=None, parentObject=None):
		self.postData = postData
		self.parentObject = parentObject
		super(CreateContentDialog, self).__init__(parent)
		if self.postData:
			self.title = _("WordPress: Edit Content")
			wx.CallAfter(self.populateData)

	def makeSettings(self, settingsSizer):
		sHelper = gui.guiHelper.BoxSizerHelper(self, sizer=settingsSizer)
		self.categories = []
		self.postTitle = sHelper.addLabeledControl(_("&Title:"), wx.TextCtrl)
		
		self.contentFormat = sHelper.addLabeledControl(_("&Content Format:"), wx.Choice, choices=[_("Plain Text"), _("HTML"), _("Markdown")])
		self.contentFormat.SetSelection(0)
		
		self.postContent = sHelper.addLabeledControl(_("&Content:"), wx.TextCtrl, style=wx.TE_MULTILINE | wx.TE_RICH2 | wx.TE_PROCESS_ENTER)
		self.postContent.Bind(wx.EVT_TEXT_ENTER, lambda e: self.postContent.WriteText('\n'))
		self.postTags = sHelper.addLabeledControl(_("&Tags (IDs):"), wx.TextCtrl)
		self.visibility = sHelper.addLabeledControl(_("&Visibility:"), wx.Choice, choices=[_("Public"), _("Private")])
		self.postPassword = sHelper.addLabeledControl(_("&Password:"), wx.TextCtrl)
		self.categoryList = sHelper.addLabeledControl(_("&Categories:"), wx.CheckListBox, choices=[_("Loading...")])
		self.contentType = sHelper.addLabeledControl(_("T&ype:"), wx.Choice, choices=[_("Post"), _("Page")])
		self.status = sHelper.addLabeledControl(_("&Status:"), wx.Choice, choices=[_("Draft"), _("Publish")])
		self.status.SetSelection(1)
		threading.Thread(target=self.fetchCategories).start()

	def fetchCategories(self):
		url = config.conf["wordpressManager"]["siteUrl"]
		auth = (config.conf["wordpressManager"]["username"], config.conf["wordpressManager"]["appPassword"])
		status, data = _make_request(f"{url}/wp-json/wp/v2/categories", auth=auth, timeout=10)
		if status == 200 and isinstance(data, list):
			self.categories = data
			wx.CallAfter(self.categoryList.Set, [c['name'] for c in self.categories])
			if self.postData:
				wx.CallAfter(self.checkCategories)

	def populateData(self):
		self.postTitle.SetValue(self.postData.get('title', {}).get('raw', self.postData.get('title', {}).get('rendered', '')))
		self.postContent.SetValue(self.postData.get('content', {}).get('raw', self.postData.get('content', {}).get('rendered', '')))
		
		if self.postData.get('type') == 'page':
			self.contentType.SetSelection(1)
		
		status = self.postData.get('status', 'draft')
		if status == 'publish': self.status.SetSelection(1)
		elif status == 'private': 
			self.status.SetSelection(1)
			self.visibility.SetSelection(1)
		else: self.status.SetSelection(0)
		
		if self.postData.get('password'):
			self.postPassword.SetValue(self.postData.get('password'))
			
		tags = self.postData.get('tags', [])
		if tags:
			self.postTags.SetValue(",".join(map(str, tags)))

	def checkCategories(self):
		post_cats = self.postData.get('categories', [])
		for i, c in enumerate(self.categories):
			if c['id'] in post_cats:
				self.categoryList.Check(i)

	def onOk(self, event):
		selectedCats = [self.categories[i]['id'] for i in range(self.categoryList.Count) if self.categoryList.IsChecked(i) and i < len(self.categories)]
		
		content_text = self.postContent.Value
		fmt = self.contentFormat.Selection
		if fmt == 0:
			content_text = content_text.replace('\n', '<br />\n')
		elif fmt == 2:
			import re
			content_text = re.sub(r'(?m)^###### (.*)$', r'<h6>\1</h6>', content_text)
			content_text = re.sub(r'(?m)^##### (.*)$', r'<h5>\1</h5>', content_text)
			content_text = re.sub(r'(?m)^#### (.*)$', r'<h4>\1</h4>', content_text)
			content_text = re.sub(r'(?m)^### (.*)$', r'<h3>\1</h3>', content_text)
			content_text = re.sub(r'(?m)^## (.*)$', r'<h2>\1</h2>', content_text)
			content_text = re.sub(r'(?m)^# (.*)$', r'<h1>\1</h1>', content_text)
			content_text = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', content_text)
			content_text = re.sub(r'\*(.*?)\*', r'<em>\1</em>', content_text)
			content_text = re.sub(r'\[(.*?)\]\((.*?)\)', r'<a href="\2">\1</a>', content_text)
			content_text = re.sub(r'(?m)^[*-]\s+(.*)$', r'<li>\1</li>', content_text)
			content_text = re.sub(r'(<li>.*?</li>(?:\n<li>.*?</li>)*)', r'<ul>\n\1\n</ul>', content_text)
			content_text = content_text.replace('\n', '<br />\n')
			content_text = content_text.replace('<br />\n<ul>', '<ul>').replace('</ul><br />\n', '</ul>')
		
		payload = {
			"title": self.postTitle.Value,
			"content": content_text,
			"status": "publish" if self.status.Selection == 1 else "draft",
			"password": self.postPassword.Value.strip()
		}
		
		cType = "posts" if self.contentType.Selection == 0 else "pages"
		
		if cType == "posts":
			payload["categories"] = selectedCats
			if self.postTags.Value: 
				try: payload["tags"] = [int(t.strip()) for t in self.postTags.Value.split(',')]
				except: pass

		if self.visibility.Selection == 1: payload["status"] = "private"
		
		if self.postData and 'id' in self.postData:
			endpoint = f"{cType}/{self.postData['id']}"
			method = "POST"
		else:
			endpoint = cType
			method = "POST"
			
		threading.Thread(target=self.parentObject.apiCall, args=(method, endpoint, payload)).start()
		super(CreateContentDialog, self).onOk(event)

class ContentManagerDialog(gui.SettingsDialog):
	title = _("WordPress: Manage Content")

	def __init__(self, parent, parentObject=None):
		self.parentObject = parentObject
		super(ContentManagerDialog, self).__init__(parent)

	def makeSettings(self, settingsSizer):
		sHelper = gui.guiHelper.BoxSizerHelper(self, sizer=settingsSizer)
		self.contents = []
		self.typeChoice = sHelper.addLabeledControl(_("Content T&ype:"), wx.Choice, choices=[_("Posts"), _("Pages")])
		self.typeChoice.SetSelection(0)
		self.typeChoice.Bind(wx.EVT_CHOICE, self.onTypeChange)
		
		self.contentList = sHelper.addLabeledControl(_("&Recent Content:"), wx.ListBox, choices=[_("Loading...")])
		btnSizer = wx.BoxSizer(wx.HORIZONTAL)
		self.btnEdit = wx.Button(self, label=_("&Edit"))
		self.btnTrash = wx.Button(self, label=_("&Trash"))
		btnSizer.Add(self.btnEdit); btnSizer.Add(self.btnTrash)
		settingsSizer.Add(btnSizer)
		
		self.btnEdit.Bind(wx.EVT_BUTTON, self.onEdit)
		self.btnTrash.Bind(wx.EVT_BUTTON, self.onTrash)
		threading.Thread(target=self.loadContent).start()

	def onTypeChange(self, evt):
		self.contentList.Clear()
		self.contentList.Append(_("Loading..."))
		threading.Thread(target=self.loadContent).start()

	def loadContent(self):
		cType = "posts" if self.typeChoice.Selection == 0 else "pages"
		url = config.conf["wordpressManager"]["siteUrl"]
		auth = (config.conf["wordpressManager"]["username"], config.conf["wordpressManager"]["appPassword"])
		status, data = _make_request(f"{url}/wp-json/wp/v2/{cType}?per_page=15&context=edit", auth=auth)
		if status == 200 and isinstance(data, list):
			self.contents = data
			items = [f"{c.get('title', {}).get('raw', c.get('title', {}).get('rendered', 'Untitled'))} ({c.get('status')})" for c in self.contents]
			wx.CallAfter(self.contentList.Set, items)
		else:
			wx.CallAfter(self.contentList.Set, [_("Failed to load or no content.")])

	def onEdit(self, evt):
		idx = self.contentList.GetSelection()
		if idx == wx.NOT_FOUND or not hasattr(self, 'contents') or idx >= len(self.contents): return
		postData = self.contents[idx]
		self.Destroy()
		d = CreateContentDialog(gui.mainFrame, postData=postData, parentObject=self.parentObject)
		d.Show()

	def onTrash(self, evt):
		idx = self.contentList.GetSelection()
		if idx == wx.NOT_FOUND or not hasattr(self, 'contents') or idx >= len(self.contents): return
		cId = self.contents[idx]['id']
		cType = "posts" if self.typeChoice.Selection == 0 else "pages"
		threading.Thread(target=self.parentObject.apiCall, args=("DELETE", f"{cType}/{cId}")).start()
		self.contentList.Delete(idx)
		del self.contents[idx]

class CommentManagerDialog(gui.SettingsDialog):
	title = _("WordPress: Manage Comments")

	def __init__(self, parent, parentObject=None):
		self.parentObject = parentObject
		super(CommentManagerDialog, self).__init__(parent)

	def makeSettings(self, settingsSizer):
		sHelper = gui.guiHelper.BoxSizerHelper(self, sizer=settingsSizer)
		self.comments = []
		self.commentList = sHelper.addLabeledControl(_("&Recent Comments:"), wx.ListBox, choices=[_("Loading...")])
		btnSizer = wx.BoxSizer(wx.HORIZONTAL)
		self.btnApprove = wx.Button(self, label=_("&Approve"))
		self.btnReply = wx.Button(self, label=_("&Reply"))
		self.btnSpam = wx.Button(self, label=_("&Spam"))
		self.btnTrash = wx.Button(self, label=_("&Trash"))
		btnSizer.Add(self.btnApprove); btnSizer.Add(self.btnReply); btnSizer.Add(self.btnSpam); btnSizer.Add(self.btnTrash)
		settingsSizer.Add(btnSizer)
		self.btnApprove.Bind(wx.EVT_BUTTON, lambda e: self.onAction("approve"))
		self.btnSpam.Bind(wx.EVT_BUTTON, lambda e: self.onAction("spam"))
		self.btnTrash.Bind(wx.EVT_BUTTON, lambda e: self.onAction("trash"))
		self.btnReply.Bind(wx.EVT_BUTTON, self.onReply)
		threading.Thread(target=self.loadComments).start()

	def loadComments(self):
		url = config.conf["wordpressManager"]["siteUrl"]
		auth = (config.conf["wordpressManager"]["username"], config.conf["wordpressManager"]["appPassword"])
		status, data = _make_request(f"{url}/wp-json/wp/v2/comments?per_page=15", auth=auth)
		if status == 200 and isinstance(data, list):
			self.comments = data
			items = [f"{c['author_name']}: {c['content']['rendered'][:50]}" for c in self.comments]
			wx.CallAfter(self.commentList.Set, items)

	def onAction(self, action):
		idx = self.commentList.GetSelection()
		if idx == wx.NOT_FOUND or not hasattr(self, 'comments') or idx >= len(self.comments): return
		cId = self.comments[idx]['id']
		threading.Thread(target=self.parentObject.apiCall, args=("POST", f"comments/{cId}", {"status": action})).start()
		self.commentList.Delete(idx)

	def onReply(self, evt):
		idx = self.commentList.GetSelection()
		if idx == wx.NOT_FOUND or not hasattr(self, 'comments') or idx >= len(self.comments): return
		cId = self.comments[idx]['id']
		postId = self.comments[idx]['post']
		
		with wx.TextEntryDialog(self, _("Enter your reply:"), _("Reply to Comment")) as dlg:
			if dlg.ShowModal() == wx.ID_OK:
				replyText = dlg.GetValue()
				if replyText:
					payload = {
						"post": postId,
						"parent": cId,
						"content": replyText,
						"status": "approved"
					}
					threading.Thread(target=self.parentObject.apiCall, args=("POST", "comments", payload)).start()

class MediaUploaderDialog(gui.SettingsDialog):
	title = _("WordPress: Upload Media")

	def __init__(self, parent, parentObject=None):
		self.parentObject = parentObject
		super(MediaUploaderDialog, self).__init__(parent)

	def makeSettings(self, settingsSizer):
		sHelper = gui.guiHelper.BoxSizerHelper(self, sizer=settingsSizer)
		
		fileSizer = wx.BoxSizer(wx.HORIZONTAL)
		self.filePath = wx.TextCtrl(self)
		btnBrowse = wx.Button(self, label=_("&Browse..."))
		btnBrowse.Bind(wx.EVT_BUTTON, self.onBrowse)
		fileSizer.Add(self.filePath, proportion=1, flag=wx.EXPAND | wx.RIGHT, border=5)
		fileSizer.Add(btnBrowse)
		
		label = wx.StaticText(self, label=_("Select &File:"))
		settingsSizer.Add(label)
		settingsSizer.Add(fileSizer, flag=wx.EXPAND | wx.BOTTOM, border=5)

	def onBrowse(self, evt):
		with wx.FileDialog(self, _("Select Media File"), wildcard="*.*", style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST) as fileDialog:
			if fileDialog.ShowModal() == wx.ID_CANCEL:
				return
			self.filePath.SetValue(fileDialog.GetPath())

	def onOk(self, event):
		path = self.filePath.Value.strip()
		if not os.path.exists(path):
			gui.messageBox(_("File does not exist."), _("Error"), wx.OK | wx.ICON_ERROR)
			return
		
		threading.Thread(target=self.uploadMedia, args=(path,)).start()
		super(MediaUploaderDialog, self).onOk(event)

	def uploadMedia(self, file_path):
		if not config.conf['wordpressManager']['siteUrl']:
			wx.CallAfter(ui.message, _("Configuration required."))
			return
			
		wx.CallAfter(ui.message, _("Uploading media, please wait..."))
		url = f"{config.conf['wordpressManager']['siteUrl']}/wp-json/wp/v2/media"
		auth = (config.conf['wordpressManager']['username'], config.conf['wordpressManager']['appPassword'])
		
		status, data = self.parentObject._make_upload_request(url, auth, file_path)
		if status == 201 and data and 'source_url' in data:
			source_url = data['source_url']
			api.copyToClip(source_url)
			wx.CallAfter(ui.message, _("Upload successful! URL copied to clipboard."))
		elif status != 0:
			wx.CallAfter(ui.message, _("Error code: {code}").format(code=status))
		else:
			wx.CallAfter(ui.message, _("Upload failed."))

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
		
		itemManage = self.wpMenu.Append(wx.ID_ANY, _("Manage Content..."))
		gui.mainFrame.sysTrayIcon.Bind(wx.EVT_MENU, self.onManageContent, itemManage)
		
		itemComm = self.wpMenu.Append(wx.ID_ANY, _("Manage Comments..."))
		gui.mainFrame.sysTrayIcon.Bind(wx.EVT_MENU, self.onComments, itemComm)
		
		itemMedia = self.wpMenu.Append(wx.ID_ANY, _("Upload Media..."))
		gui.mainFrame.sysTrayIcon.Bind(wx.EVT_MENU, self.onUploadMedia, itemMedia)
		
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
		d = CreateContentDialog(gui.mainFrame, parentObject=self)
		d.Show()

	def onManageContent(self, evt):
		d = ContentManagerDialog(gui.mainFrame, parentObject=self)
		d.Show()

	def onComments(self, evt):
		d = CommentManagerDialog(gui.mainFrame, parentObject=self)
		d.Show()

	def onUploadMedia(self, evt):
		d = MediaUploaderDialog(gui.mainFrame, parentObject=self)
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
		status, _data = _make_request(url, auth=auth, method=method, data=data, timeout=15)
		
		if status in [200, 201]:
			wx.CallAfter(ui.message, _("Operation successful."))
		elif status != 0:
			wx.CallAfter(ui.message, _("Error code: {code}").format(code=status))
		else:
			wx.CallAfter(ui.message, _("Connection failed."))

	def _make_upload_request(self, url, auth, file_path, timeout=60):
		headers = {}
		if auth and len(auth) == 2 and auth[0]:
			auth_str = f"{auth[0]}:{auth[1]}"
			encoded_auth = base64.b64encode(auth_str.encode('utf-8')).decode('ascii')
			headers['Authorization'] = f"Basic {encoded_auth}"
		
		mime_type, _ = mimetypes.guess_type(file_path)
		if not mime_type:
			mime_type = "application/octet-stream"
			
		headers['Content-Type'] = mime_type
		
		safe_filename = os.path.basename(file_path).encode('ascii', 'ignore').decode('ascii')
		if not safe_filename: safe_filename = "uploaded_media"
		headers['Content-Disposition'] = f'attachment; filename="{safe_filename}"'
		
		try:
			with open(file_path, "rb") as f:
				data = f.read()
			req = urllib.request.Request(url, data=data, headers=headers, method="POST")
			with urllib.request.urlopen(req, timeout=timeout) as response:
				return response.getcode(), json.loads(response.read().decode('utf-8'))
		except urllib.error.HTTPError as e:
			try:
				return e.code, json.loads(e.read().decode('utf-8'))
			except:
				return e.code, None
		except Exception:
			return 0, None

	def terminate(self):
		try: self.menu.Remove(self.mainItem)
		except: pass