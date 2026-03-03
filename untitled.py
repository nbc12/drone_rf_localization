#!/usr/bin/env python3
# -*- coding: utf-8 -*-

#
# SPDX-License-Identifier: GPL-3.0
#
# GNU Radio Python Flow Graph
# Title: Not titled yet
# GNU Radio version: 3.10.12.0

from PyQt5 import Qt
from gnuradio import qtgui
from PyQt5 import QtCore
from gnuradio import aoa
from gnuradio import blocks
from gnuradio import gr
from gnuradio.filter import firdes
from gnuradio.fft import window
import sys
import signal
from PyQt5 import Qt
from argparse import ArgumentParser
from gnuradio.eng_arg import eng_float, intx
from gnuradio import eng_notation
import bladeRF
import time
import sip
import threading



class untitled(gr.top_block, Qt.QWidget):

    def __init__(self):
        gr.top_block.__init__(self, "Not titled yet", catch_exceptions=True)
        Qt.QWidget.__init__(self)
        self.setWindowTitle("Not titled yet")
        qtgui.util.check_set_qss()
        try:
            self.setWindowIcon(Qt.QIcon.fromTheme('gnuradio-grc'))
        except BaseException as exc:
            print(f"Qt GUI: Could not set Icon: {str(exc)}", file=sys.stderr)
        self.top_scroll_layout = Qt.QVBoxLayout()
        self.setLayout(self.top_scroll_layout)
        self.top_scroll = Qt.QScrollArea()
        self.top_scroll.setFrameStyle(Qt.QFrame.NoFrame)
        self.top_scroll_layout.addWidget(self.top_scroll)
        self.top_scroll.setWidgetResizable(True)
        self.top_widget = Qt.QWidget()
        self.top_scroll.setWidget(self.top_widget)
        self.top_layout = Qt.QVBoxLayout(self.top_widget)
        self.top_grid_layout = Qt.QGridLayout()
        self.top_layout.addLayout(self.top_grid_layout)

        self.settings = Qt.QSettings("gnuradio/flowgraphs", "untitled")

        try:
            geometry = self.settings.value("geometry")
            if geometry:
                self.restoreGeometry(geometry)
        except BaseException as exc:
            print(f"Qt GUI: Could not restore geometry: {str(exc)}", file=sys.stderr)
        self.flowgraph_started = threading.Event()

        ##################################################
        # Variables
        ##################################################
        self.num_antennas = num_antennas = 6
        self.dwell_time = dwell_time = 50e-6
        self.samp_rate = samp_rate = 1e6
        self.cycle_period = cycle_period = (dwell_time * (num_antennas + 1))
        self.sync_threshold = sync_threshold = 0.2
        self.recording = recording = 1
        self.enabled = enabled = 0
        self.cycle_samples = cycle_samples = cycle_period * samp_rate
        self.center_freq = center_freq = 2.462e9
        self.bw = bw = 550e3
        self.bladerf_gain = bladerf_gain = 60

        ##################################################
        # Blocks
        ##################################################

        self._samp_rate_range = qtgui.Range(100e3, 40e6, 1e6, 1e6, 200)
        self._samp_rate_win = qtgui.RangeWidget(self._samp_rate_range, self.set_samp_rate, "samp_rate", "counter_slider", float, QtCore.Qt.Horizontal)
        self.top_layout.addWidget(self._samp_rate_win)
        _enabled_check_box = Qt.QCheckBox("enabled")
        self._enabled_choices = {True: 0, False: 1}
        self._enabled_choices_inv = dict((v,k) for k,v in self._enabled_choices.items())
        self._enabled_callback = lambda i: Qt.QMetaObject.invokeMethod(_enabled_check_box, "setChecked", Qt.Q_ARG("bool", self._enabled_choices_inv[i]))
        self._enabled_callback(self.enabled)
        _enabled_check_box.stateChanged.connect(lambda i: self.set_enabled(self._enabled_choices[bool(i)]))
        self.top_layout.addWidget(_enabled_check_box)
        self._center_freq_range = qtgui.Range(2.0e9, 6e9, 1e6, 2.462e9, 200)
        self._center_freq_win = qtgui.RangeWidget(self._center_freq_range, self.set_center_freq, "center_freq", "counter_slider", float, QtCore.Qt.Horizontal)
        self.top_layout.addWidget(self._center_freq_win)
        self._bw_range = qtgui.Range(1e3, 60e6, 10e3, 550e3, 200)
        self._bw_win = qtgui.RangeWidget(self._bw_range, self.set_bw, "bw", "counter_slider", float, QtCore.Qt.Horizontal)
        self.top_layout.addWidget(self._bw_win)
        self._bladerf_gain_range = qtgui.Range(-1, 60, 1, 60, 200)
        self._bladerf_gain_win = qtgui.RangeWidget(self._bladerf_gain_range, self.set_bladerf_gain, "BladeRF Gain", "counter_slider", float, QtCore.Qt.Horizontal)
        self.top_layout.addWidget(self._bladerf_gain_win)
        self._sync_threshold_range = qtgui.Range(0.0, 1.0, 1e-2, 0.2, 200)
        self._sync_threshold_win = qtgui.RangeWidget(self._sync_threshold_range, self.set_sync_threshold, "sync_threshold", "counter_slider", float, QtCore.Qt.Horizontal)
        self.top_layout.addWidget(self._sync_threshold_win)
        _recording_check_box = Qt.QCheckBox("recording")
        self._recording_choices = {True: 0, False: 1}
        self._recording_choices_inv = dict((v,k) for k,v in self._recording_choices.items())
        self._recording_callback = lambda i: Qt.QMetaObject.invokeMethod(_recording_check_box, "setChecked", Qt.Q_ARG("bool", self._recording_choices_inv[i]))
        self._recording_callback(self.recording)
        _recording_check_box.stateChanged.connect(lambda i: self.set_recording(self._recording_choices[bool(i)]))
        self.top_layout.addWidget(_recording_check_box)
        self.qtgui_sink_x_0 = qtgui.sink_c(
            1024, #fftsize
            window.WIN_BLACKMAN_hARRIS, #wintype
            0, #fc
            samp_rate, #bw
            "", #name
            True, #plotfreq
            True, #plotwaterfall
            True, #plottime
            True, #plotconst
            None # parent
        )
        self.qtgui_sink_x_0.set_update_time(1.0/10)
        self._qtgui_sink_x_0_win = sip.wrapinstance(self.qtgui_sink_x_0.qwidget(), Qt.QWidget)

        self.qtgui_sink_x_0.enable_rf_freq(False)

        self.top_layout.addWidget(self._qtgui_sink_x_0_win)
        self._dwell_time_range = qtgui.Range(40e-6, 100e-6, 1e-6, 50e-6, 200)
        self._dwell_time_win = qtgui.RangeWidget(self._dwell_time_range, self.set_dwell_time, "dwell_time", "counter_slider", float, QtCore.Qt.Horizontal)
        self.top_layout.addWidget(self._dwell_time_win)
        self.blocks_selector_0_0_0 = blocks.selector(gr.sizeof_gr_complex*1,0,enabled)
        self.blocks_selector_0_0_0.set_enabled(True)
        self.blocks_selector_0_0 = blocks.selector(gr.sizeof_gr_complex*1,0,enabled)
        self.blocks_selector_0_0.set_enabled(True)
        self.blocks_null_sink_0_0_0_0 = blocks.null_sink(gr.sizeof_gr_complex*1)
        self.blocks_null_sink_0_0_0 = blocks.null_sink(gr.sizeof_gr_complex*1)
        self.blocks_null_sink_0_0 = blocks.null_sink(gr.sizeof_gr_complex*1)
        self.bladeRF_source_0 = bladeRF.source(
            args="numchan=" + str(1)
                 + ",metadata=" + 'False'
                 + ",bladerf=" +  str('')
                 + ",verbosity=" + 'verbose'
                 + ",feature=" + 'default'
                 + ",sample_format=" + '16bit'
                 + ",fpga=" + str('/home/noah/hostedxA4.rbf')
                 + ",fpga-reload=" + 'False'
                 + ",use_ref_clk=" + 'False'
                 + ",ref_clk=" + str(int(10e6))
                 + ",buflen=" + str(int(4096))
                 + ",buffers=" + str(int(512))
                 + ",in_clk=" + 'ONBOARD'
                 + ",out_clk=" + str(False)
                 + ",use_dac=" + 'False'
                 + ",dac=" + str(10000)
                 + ",xb200=" + 'none'
                 + ",tamer=" + 'internal'
                 + ",sampling=" + 'internal'
                 + ",lpf_mode="+'disabled'
                 + ",smb="+str(int(38.4e6))
                 + ",dc_calibration="+'LPF_TUNING'
                 + ",trigger0="+'False'
                 + ",trigger_role0="+'master'
                 + ",trigger_signal0="+'J51_1'
                 + ",trigger1="+'False'
                 + ",trigger_role1="+'master'
                 + ",trigger_signal1="+'J51_1'
                 + ",bias_tee0="+'False'
                 + ",bias_tee1="+'False'


        )
        self.bladeRF_source_0.set_sample_rate(samp_rate)
        self.bladeRF_source_0.set_center_freq(center_freq,0)
        self.bladeRF_source_0.set_bandwidth(bw,0)
        self.bladeRF_source_0.set_dc_offset_mode(0, 0)
        self.bladeRF_source_0.set_iq_balance_mode(0, 0)
        self.bladeRF_source_0.set_gain_mode(False, 0)
        self.bladeRF_source_0.set_gain(bladerf_gain, 0)
        self.bladeRF_source_0.set_if_gain(0, 0)
        self.aoa_chunk_tagger_1 = aoa.chunk_tagger(
            samp_rate=samp_rate,
            seconds_per_chunk=1.0,
            base_path='/home/noah/droneflight_adam',
            files_per_folder=1000
        )
        self.aoa_chunk_tagger_0 = aoa.chunk_tagger(
            samp_rate=samp_rate,
            seconds_per_chunk=1.0,
            base_path='.',
            files_per_folder=1000
        )


        ##################################################
        # Connections
        ##################################################
        self.connect((self.aoa_chunk_tagger_0, 0), (self.aoa_chunk_tagger_1, 0))
        self.connect((self.aoa_chunk_tagger_1, 0), (self.blocks_null_sink_0_0_0_0, 0))
        self.connect((self.bladeRF_source_0, 0), (self.blocks_selector_0_0, 0))
        self.connect((self.blocks_selector_0_0, 1), (self.blocks_null_sink_0_0, 0))
        self.connect((self.blocks_selector_0_0, 0), (self.blocks_selector_0_0_0, 0))
        self.connect((self.blocks_selector_0_0, 0), (self.qtgui_sink_x_0, 0))
        self.connect((self.blocks_selector_0_0_0, 0), (self.aoa_chunk_tagger_0, 0))
        self.connect((self.blocks_selector_0_0_0, 1), (self.blocks_null_sink_0_0_0, 0))


    def closeEvent(self, event):
        self.settings = Qt.QSettings("gnuradio/flowgraphs", "untitled")
        self.settings.setValue("geometry", self.saveGeometry())
        self.stop()
        self.wait()

        event.accept()

    def get_num_antennas(self):
        return self.num_antennas

    def set_num_antennas(self, num_antennas):
        self.num_antennas = num_antennas
        self.set_cycle_period((self.dwell_time * (self.num_antennas + 1)))

    def get_dwell_time(self):
        return self.dwell_time

    def set_dwell_time(self, dwell_time):
        self.dwell_time = dwell_time
        self.set_cycle_period((self.dwell_time * (self.num_antennas + 1)))

    def get_samp_rate(self):
        return self.samp_rate

    def set_samp_rate(self, samp_rate):
        self.samp_rate = samp_rate
        self.set_cycle_samples(self.cycle_period * self.samp_rate)
        self.bladeRF_source_0.set_sample_rate(self.samp_rate)
        self.qtgui_sink_x_0.set_frequency_range(0, self.samp_rate)

    def get_cycle_period(self):
        return self.cycle_period

    def set_cycle_period(self, cycle_period):
        self.cycle_period = cycle_period
        self.set_cycle_samples(self.cycle_period * self.samp_rate)

    def get_sync_threshold(self):
        return self.sync_threshold

    def set_sync_threshold(self, sync_threshold):
        self.sync_threshold = sync_threshold

    def get_recording(self):
        return self.recording

    def set_recording(self, recording):
        self.recording = recording
        self._recording_callback(self.recording)

    def get_enabled(self):
        return self.enabled

    def set_enabled(self, enabled):
        self.enabled = enabled
        self._enabled_callback(self.enabled)
        self.blocks_selector_0_0.set_output_index(self.enabled)
        self.blocks_selector_0_0_0.set_output_index(self.enabled)

    def get_cycle_samples(self):
        return self.cycle_samples

    def set_cycle_samples(self, cycle_samples):
        self.cycle_samples = cycle_samples

    def get_center_freq(self):
        return self.center_freq

    def set_center_freq(self, center_freq):
        self.center_freq = center_freq
        self.bladeRF_source_0.set_center_freq(self.center_freq, 0)

    def get_bw(self):
        return self.bw

    def set_bw(self, bw):
        self.bw = bw
        self.bladeRF_source_0.set_bandwidth(self.bw, 0)

    def get_bladerf_gain(self):
        return self.bladerf_gain

    def set_bladerf_gain(self, bladerf_gain):
        self.bladerf_gain = bladerf_gain
        self.bladeRF_source_0.set_gain(self.bladerf_gain, 0)




def main(top_block_cls=untitled, options=None):

    qapp = Qt.QApplication(sys.argv)

    tb = top_block_cls()

    tb.start()
    tb.flowgraph_started.set()

    tb.show()

    def sig_handler(sig=None, frame=None):
        tb.stop()
        tb.wait()

        Qt.QApplication.quit()

    signal.signal(signal.SIGINT, sig_handler)
    signal.signal(signal.SIGTERM, sig_handler)

    timer = Qt.QTimer()
    timer.start(500)
    timer.timeout.connect(lambda: None)

    qapp.exec_()

if __name__ == '__main__':
    main()
