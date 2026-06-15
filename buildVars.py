# Build customizations
# Change this file instead of SConstruct or manifest files, whenever possible.

from site_scons.site_tools.NVDATool.typings import AddonInfo, BrailleTables, SymbolDictionaries
from site_scons.site_tools.NVDATool.utils import _


addon_info = AddonInfo(
	addon_name="wordpressManager",
	# Translators: Summary/title for this add-on
	addon_summary=_("WordPress Manager"),
	# Translators: Long description for this add-on
	addon_description=_(
		"Professional tool that allows you to manage your WordPress site via REST API directly from NVDA. Supports Markdown and HTML content, media uploads, and multi-site configuration."
	),
	addon_version="20.0",
	# Translators: What's new content for the add-on version
	addon_changelog=_(
		"- Added support for multiple saved site profiles.\n"
		"- Added ability to write posts in Markdown.\n"
		"- Added Media Upload, Manage Content (Edit/Trash), and Reply to Comments features.\n"
		"- Removed external requests library to guarantee full 64-bit and 32-bit Python cross-compatibility for NVDA 2026.1 and NVDA 2025.x.\n"
		"- Restructured add-on architecture to conform to standard NVDA Add-on template."
	),
	addon_author="Volkan Ozdemir Software Services <bilgi@volkan-ozdemir.com.tr>, Fauzan, S.Kom. <surel@fauzanaja.com>",
	addon_url="https://www.volkan-ozdemir.com.tr",
	addon_sourceURL="",
	addon_docFileName="readme.html",
	addon_minimumNVDAVersion="2021.3",
	addon_lastTestedNVDAVersion="2026.1",
	addon_updateChannel=None,
	addon_license="GPL-2.0",
	addon_licenseURL="https://www.gnu.org/licenses/gpl-2.0.html",
)

pythonSources: list[str] = [
	"addon/globalPlugins/wordpressmanager.py",
]

i18nSources: list[str] = pythonSources + ["buildVars.py"]

excludedFiles: list[str] = []

baseLanguage: str = "en"

markdownExtensions: list[str] = []

brailleTables: BrailleTables = {}

symbolDictionaries: SymbolDictionaries = {}
