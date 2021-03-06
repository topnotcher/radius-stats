#!/usr/bin/env python
import csv
import argparse

def csv_row_get_identifier(row):
	"""
	The (client,server,sport,dport) tuple identifies packets of a RADIUS
	"transaction". I'm assuming the server's port is always 1812.
	"""
	identifier = {'client': '', 'server': '', 'port': 0, 'id' : 0}

	if row['Destination Port'] == '1812': 
		identifier['server'] = row['Destination']
		identifier['client'] = row['Source']
		identifier['port'] = int(row['Source Port'])
	else:
		identifier['server'] = row['Source']
		identifier['client'] = row['Destination']
		identifier['port'] = int(row['Destination Port'])

	identifier['id'] = int(row['Identifier'])
	return identifier

def csv_row_get_txn_info(row):
	txn = csv_row_get_identifier(row)
	txn['time'] = float(row['Time'])

	keep_fields = ['Code', 'User-Name','Calling-Station-Id','Aruba-AP-Group','Aruba-Device-Type']
	for field in keep_fields:
		if field in row:
			txn[field] = row[field]

	return txn


class RadiusTransactions(object):
	STATUS_OK = 0
	STATUS_DUPLICATE = 1
	STATUS_TIMEOUT = 2
	STATUS_INVALID = 3

	def __init__(self):
		self.txns  = {}

	def init_txn_dict(self,txn):

		if txn['server'] not in self.txns:
			self.txns[txn['server']] = {}

		if txn['client'] not in self.txns[txn['server']]:
			self.txns[txn['server']][txn['client']] = {}

		if txn['port'] not in self.txns[txn['server']][txn['client']]:
			self.txns[txn['server']][txn['client']][txn['port']] = {}

	def get_txn(self,txn):
		id = txn['id']
		client = txn['client']
		server = txn['server']
		port = txn['port']
		self.init_txn_dict(txn)

		if id in self.txns[server][client][port]:
			return self.txns[server][client][port][id]
		else:
			return None
	
	def add_request(self, txn):
		txn['start_time'] = txn['time']
		del txn['time']
		self.txns[txn['server']][txn['client']][txn['port']][txn['id']] = txn

	def begin(self,txn):
		self.init_txn_dict(txn)
		saved_txn = self.get_txn(txn)
		txn['requests'] = 1

		if saved_txn is None:
			self.add_request(txn)
			return (self.STATUS_OK, None)

		# Assume anytime there is a conflicting MAC, this represents a timeout
		elif saved_txn['Calling-Station-Id'] != txn['Calling-Station-Id'] or txn['time'] - saved_txn['start_time'] > 30:
			self.add_request(txn)
			
			return (self.STATUS_TIMEOUT, txn)

		# same txn, same MAC address, within 30 seconds. This is a repeated request.
		else:
			saved_txn['requests'] += 1
			return (self.STATUS_DUPLICATE, saved_txn)

	def finish(self,txn):
		saved_txn = self.get_txn(txn)

		if saved_txn is None:
			return (self.STATUS_INVALID, None)

		else:
			saved_txn['end_time'] = txn['time']
			saved_txn['duration'] = saved_txn['end_time'] - saved_txn['start_time']
			saved_txn['Code'] = txn['Code']

		try:
			del self.txns[txn['server']][txn['client']][txn['port']][txn['id']]
		except KeyError:
			pass


		return (self.STATUS_OK, saved_txn)

	def count(self):
		size = 0
		for server in self.txns:
			for client in self.txns[server]:
				for port in self.txns[server][client]:
					size += len(self.txns[server][client][port])

		return size

class RadiusStats(object):
	def __init__(self):
		self.stats = {}

	def update_server_stats(self,log,stats):
		stats['requests'] += 1

		if log['Code'] == 'Access-Accept':
			stats['accept'] += 1
		elif log['Code'] == 'Access-Reject':
			stats['reject'] += 1
		elif log['Code'] == 'Access-Challenge':
			stats['challenge'] += 1

		time = float(log['duration'])
		fives = int(time/5)

		if fives < 5:
			stats['times'][fives] += 1
		else:
			stats['times'][5] += 1

		stats['time'] += time

	def update(self, log):
		if log['server'] not in self.stats:
			self.stats[log['server']] = {'requests':0, 'reject':0, 'challenge':0, 'accept':0, 'time': 0, 'times': [0,0,0,0,0,0]}

		self.update_server_stats(log,self.stats[log['server']])

	def print_stats(self):
		for server in self.stats:
			print '-------------------------------------------'
			print 'Statistics for %s' % (server)
			self.print_server_stats(self.stats[server])

	def print_server_stats(self,stats):
		std = ['requests','reject','challenge','accept']

		for field in std:
			print '%s: %d' % (field, stats[field])

		time = round(stats['time']/stats['requests'],4)
		
		print('Average Response Time: %fs' % (time)) 
		print('Breakdown of response times: ')
		
		for i in range(0,5):
			lower = i*5
			upper = i*5+5;
			print '\t %d-%d seconds: %d' % (lower,upper,stats['times'][i])

		print '\t >25 seconds: %d' % (stats['times'][5])


		
def main(log_file, result_file):
	txns = RadiusTransactions()
	stats = RadiusStats()
	results = None

	log = csv.DictReader( open(log_file) )

	for row in log:
		code = row['Code']
		if row['Protocol'] != 'RADIUS':
			continue

		txn = csv_row_get_txn_info(row)

		if code == 'Access-Request':
			code, old_txn = txns.begin(txn)
			
			if code == txns.STATUS_TIMEOUT:
				print 'TXN timeout %s -> %s; (%d); old/new: %s/%s %s/%s; %d requests; %fs ago' % (
						old_txn['client'], old_txn['server'], old_txn['id'], old_txn['User-Name'],
						txn['User-Name'], old_txn['Calling-Station-Id'], txn['Calling-Station-Id'],
						old_txn['requests'],txn['time'] - old_txn['start_time']
				)
			elif code == txns.STATUS_DUPLICATE:
				print 'Duplicate request %s -> %s; (%d); client: %s %s; %d requests; first: %fs ago' % (
						txn['client'], txn['server'], txn['id'], txn['User-Name'], txn['Calling-Station-Id'],
						old_txn['requests'],txn['time'] - old_txn['start_time']
				)

		elif code in ['Access-Accept','Access-Reject','Access-Challenge']:
			code, result = txns.finish(txn)

			if code == txns.STATUS_INVALID:
				print "%s: invalid txn state client: %s; server: %s" % (txn['Code'],txn['client'],txn['server'])
				continue

			if results is None:
				results = csv.DictWriter(open(result_file,'wb'),result.keys())
				results.writeheader()

			stats.update(result)
			results.writerow(result)
		else:
			print "UNHANDLED CODE"
			exit(1)

	# This is not necessarily informational as there could be requests that are
	# too new to have a response. A better method would be to search for timed
	# out requests at the end since at present the only timeout detection is
	# when the RADIUS Identifier is reused.
	print "%d unfinished requests" % (txns.count())

	stats.print_stats()

if __name__ == '__main__':
	parser = argparse.ArgumentParser(description='Analyze response times from a packet capture (exported as CSV in wireshark) of RADIUS authentications.')
	parser.add_argument('input_file', type=str, help="The CSV file to read from")
	parser.add_argument('result_file', type=str, help="A CSV file to write to.")
	args = parser.parse_args()

	main(args.input_file, args.result_file)


