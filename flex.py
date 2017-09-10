#!/usr/bin/env python
#
# Copyright 2006,2007,2009 Free Software Foundation, Inc.
#
# This file is part of GNU Radio
#
# GNU Radio is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3, or (at your option)
# any later version.
#
# GNU Radio is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with GNU Radio; see the file COPYING.  If not, write to
# the Free Software Foundation, Inc., 51 Franklin Street,
# Boston, MA 02110-1301, USA.
#
#   Modified by Mothran for use with HackRF
#   Modified by Dennis Mantz to work with GNU Radio 3.7
from gnuradio import gr, eng_notation, filter, pager, blocks
from gnuradio.eng_option import eng_option
from optparse import OptionParser
from string import split, join, printable
import sys
import osmosdr


class app_top_block(gr.top_block):
	def __init__(self, options, queue):
		gr.top_block.__init__(self, "flex_hackrf")

		# Set up HackRF source
		self.u = osmosdr.source( args="numchan=" + str(1) + " " + "" )
		self.u.set_freq_corr(0, 0)
		self.u.set_dc_offset_mode(0, 0)
		self.u.set_iq_balance_mode(0, 0)
		self.u.set_gain_mode(False, 0)
		self.u.set_gain(0, 0)
		self.u.set_if_gain(20, 0)
		self.u.set_bb_gain(20, 0)
		self.u.set_antenna("", 0)
		self.u.set_bandwidth(0, 0)

		# Tune hackRF
		r = self.u.set_center_freq(options.freq+options.calibration, 0)
		if not r:
			frange = self.u.get_freq_range()
			sys.stderr.write(("\nRequested frequency (%f) out or range [%f, %f]\n") % \
								 (freq, frange.start(), frange.stop()))
			sys.exit(1)

		if options.verbose:
			print "Tuned to center frequency", (options.freq+options.calibration)/1e6, "MHz"

		# Grab >=3 MHz of spectrum, evenly divisible by 25 KHz channels
		# (A UHD facility to get sample rate range and granularity would be useful)

		self.u.set_sample_rate(3.125e6) # Works if USRP is 100 Msps and can decimate by 32
		rate = self.u.get_sample_rate()

		if rate != 3.125e6:
			self.u.set_sample_rate(3.2e6) # Works if USRP is 64 Msps and can decimate by 20
			rate = self.u.get_sample_rate()
			if (rate != 3.2e6):
				print "Unable to set required sample rate for >= 3MHz of 25 KHz channels."
				sys.exit(1)

		self.nchan = int(rate/25e3)
		if options.verbose:
			print "\nReceiving", rate/1e6, "MHz of bandwidth containing", self.nchan, "baseband channels."

		taps = filter.firdes.low_pass(1.0,1.0,1.0/self.nchan*0.4,1.0/self.nchan*0.1,filter.firdes.WIN_HANN)

		if options.verbose:
			print "Channel filter has", len(taps), "taps"

		self.bank = filter.analysis_filterbank(self.nchan, taps)
		self.connect(self.u, self.bank)

		mid_chan = int(self.nchan/2)
		for i in range(self.nchan):
			if i < mid_chan:
				freq = options.freq+i*25e3
			else:
				freq = options.freq-(self.nchan-i)*25e3

			if (freq < 929.0e6 or freq > 932.0e6):
				self.connect((self.bank, i), blocks.null_sink(gr.sizeof_gr_complex))
			else:
				self.connect((self.bank, i), pager.flex_demod(queue, freq, options.verbose))

def get_options():
	parser = OptionParser(option_class=eng_option)
	parser.add_option('-f', '--freq', type="eng_float", default=931.95e6,
		help="Set receive frequency to FREQ [default=%default]",
		metavar="FREQ")
	parser.add_option("-c",   "--calibration", type="eng_float", default=0.0,
		help="set frequency offset to Hz", metavar="Hz")
	parser.add_option("-v", "--verbose", action="store_true", default=False)
	parser.add_option("", "--nchan", type="int", default=None,
		help="set to number of channels in capture file", metavar="nchan")

	(options, args) = parser.parse_args()

	return (options, args)

def make_trans_table():
	table = 256 * ['.']
	for i in range(256):
		if (i < 32):
			table[i] = '.'
		else:
			table[i] = chr(i)
	return ''.join(table)

def main():

	(options, args) = get_options()

	queue = gr.msg_queue()
	tb = app_top_block(options, queue)
	tb.start()

	conversion_table = make_trans_table()
	while 1:
		msg = queue.delete_head() # Blocking read
		if msg.type() != 0:
			break
		
		page = split(msg.to_string(), chr(128))
		if page[2] == "ALN":
			print page[0] + " | " + page[3].replace("\n", "")

	tb.end()

if __name__ == "__main__":
	main()
