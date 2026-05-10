from mw2wj.template_plugins.builtins.box_code import BoxCodePlugin
from mw2wj.template_plugins.builtins.box_file import BoxFilePlugin
from mw2wj.template_plugins.builtins.cmd import CmdPlugin
from mw2wj.template_plugins.builtins.code_block import CodeBlockPlugin
from mw2wj.template_plugins.builtins.commandline import CommandlinePlugin
from mw2wj.template_plugins.builtins.filename import FilenamePlugin
from mw2wj.template_plugins.builtins.redirect import RedirectPlugin
from mw2wj.template_plugins.registry import registry

# Auto-register builtin template plugins.
#
# Aliases: some templates have multiple names that resolve to the same
# MediaWiki page (redirects, renames) or common typos that have spread
# through copy-paste across the wiki.  Registering an alias via
# registry._plugins["variant"] = plugin_instance ensures both forms are
# handled identically without duplicating the plugin class.
registry.register(BoxCodePlugin())
box_file = BoxFilePlugin()
registry.register(box_file)
# Alias: {{Box File Scroll|...}} redirects to Template:Box File
registry._plugins["box file scroll"] = box_file
registry.register(CodeBlockPlugin())
cmd = CmdPlugin()
registry.register(cmd)
# Alias: common typo "cmq" (q/w keyboard slip) found on real-world pages
registry._plugins["cmq"] = cmd
cmdline = CommandlinePlugin()
registry.register(cmdline)
# Alias: common typo "comandline" (single 'm') found on real-world pages
registry._plugins["comandline"] = cmdline
registry.register(FilenamePlugin())
registry.register(RedirectPlugin())
