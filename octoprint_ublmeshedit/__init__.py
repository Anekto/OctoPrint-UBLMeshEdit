# coding=utf-8
from __future__ import absolute_import

import octoprint.plugin

class UBLMeshEditPlugin(octoprint.plugin.AssetPlugin,
						octoprint.plugin.SettingsPlugin,
						octoprint.plugin.SimpleApiPlugin,
						octoprint.plugin.TemplatePlugin):

	def __init__(self):
		self.wait_mesh = False
		self.mesh_data = None
		self.in_topo = False
		self.slot_num = None
		self.wait_ok = False
		self.skip_first = False
		self.skip_line = False
		self.not_ubl = False

	##~~ SettingsPlugin mixin
	def get_settings_defaults(self):
		return dict(
			export_gcode_filename="Restore Mesh - {printerName} - {dateTime}.gcode",
			hide_non_ubl_warning=False,
			circular_bed=False,
			circular_bed_inset_perc=0.0,
			show_mesh_headers=False
		)

	def get_template_configs(self):
		return [
			dict(type="settings", custom_bindings=False)
		]

	##~~ AssetPlugin mixin

	def get_assets(self):
		return dict(
			js=["js/ublmeshedit.js"],
			css=["css/ublmeshedit.css"]
		)

	##~~ SimpleApiPlugin mixin

	def get_api_commands(self):
		return {'wait_command': []}

	def on_api_command(self, command, _):
		if command == 'wait_command':
			self.wait_ok = True

	def on_gcode_sending(self, _, __, cmd, ___, ____, _____=None, ______=None, *_______, **________):
		if cmd == 'M420 V1 T1':
			self.wait_mesh = True
		return None

	def on_gcode_recieved(self, _, line, *__, **___):
		if not self.wait_g29 or line.strip() == 'wait' or line.strip() == 'Not SD printing':
			return line  # early out

		if line.strip() == 'Mesh Bed Leveling has no data.':
			self.mesh_data = None
			self.wait_g29 = False
			self.send_mesh_collected_event()
		elif 'Measured points:' in line:
			self.mesh_data = []  # initialize empty mesh data
			self.g29_mesh_line = -1  # ready for row count
		elif self.g29_mesh_line is not None and self.g29_mesh_line > -1:
			if self.g29_mesh_line == 0:
				parts = line.strip().split()
				if len(parts) > 2 and parts[1] == 'points:':
					size = len(parts) - 2
					if size != self._settings.get_int(['grid_size']):
						self._logger.info(f"Mesh size {size} doesn't match plugin setting {self._settings.get_int(['grid_size'])}, changing to match")
						self._settings.set_int(['grid_size'], size)
						self._settings.save(trigger_event=True)

			try:
				# Parse each line, handling potential leading/trailing spaces
				parts = line.strip().split()
				row_index = int(parts[0])
				if row_index == self.g29_mesh_line:
					values = [float(x) for x in parts[1:]]
					self.mesh_data.append(values)
					self.g29_mesh_line += 1
			except (ValueError, IndexError):
				self._logger.debug(f"Skipping line: {line.strip()}")

			if self.g29_mesh_line >= self._settings.get_int(['grid_size']):
				self._logger.info("Got all mesh data")
				self.wait_g29 = False
				self.g29_mesh_line = None
				self.send_mesh_collected_event()

		elif self.g29_mesh_line == -1:
			try:
				self.g29_mesh_line = int(line[:line.find(':')])
			except:
				pass

		return line

	def on_atcommand_sending(self, _, __, cmd, ___, ____=None, *_____, **______):
		if cmd == 'UBLMESHEDIT':
			self.wait_mesh = True

	def send_command_complete_event(self):
		event = octoprint.events.Events.PLUGIN_UBLMESHEDIT_COMMAND_COMPLETE
		self._event_bus.fire(event)

	def send_mesh_collected_event(self):
		event = octoprint.events.Events.PLUGIN_UBLMESHEDIT_MESH_READY
		if self.mesh_data is None:
			data = {'result': 'no mesh'}
		else:
			data = {'result': 'ok', 'data': self.mesh_data, 'gridSize': len(self.mesh_data), 'saveSlot': self.slot_num}
		if self.not_ubl:
			data['notUBL'] = True
		self._event_bus.fire(event, payload=data)

	def register_custom_events(*_, **__):
		return ["mesh_ready", "command_complete"]

	##~~ Softwareupdate hook

	def get_update_information(self):
		return dict(
			ublmeshedit=dict(
				displayName="UBL Mesh Editor",
				displayVersion=self._plugin_version,

				# version check: github repository
				type="github_release",
				user="Anekto",
				repo="OctoPrint-UBLMeshEdit",
				current=self._plugin_version,

				# update method: pip
				pip="https://github.com/Anekto/OctoPrint-UBLMeshEdit/archive/{target_version}.zip",

				# release channels
				stable_branch=dict(
					name="Stable",
					branch="main",
					comittish=["main"]
				),
				prerelease_branches=[
					{
						"name": "Release Candidate",
						"branch": "rc",
						"committish": ["rc", "main"]
					}
				]
			)
		)


__plugin_name__ = "UBL Mesh Editor"
__plugin_pythoncompat__ = ">=2.7,<4"

def __plugin_load__():
	global __plugin_implementation__
	__plugin_implementation__ = UBLMeshEditPlugin()

	global __plugin_hooks__
	__plugin_hooks__ = {
		"octoprint.plugin.softwareupdate.check_config": __plugin_implementation__.get_update_information,
		"octoprint.comm.protocol.gcode.received": __plugin_implementation__.on_gcode_recieved,
		"octoprint.comm.protocol.gcode.sending": __plugin_implementation__.on_gcode_sending,
		"octoprint.comm.protocol.atcommand.sending": __plugin_implementation__.on_atcommand_sending,
		"octoprint.events.register_custom_events": __plugin_implementation__.register_custom_events
	}
