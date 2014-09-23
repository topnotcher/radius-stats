import csv

LOG_FILE = 'radius-20140922-1150_1230.csv'
RESULT_FILE = "result.csv"

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

log = csv.DictReader( open(LOG_FILE) )

class RadiusTransactions(object):
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
	
	def begin_txn(self, txn):
		txn['start_time'] = txn['time']
		del txn['time']
		self.txns[txn['server']][txn['client']][txn['port']][txn['id']] = txn

	def add_request(self,txn):
		self.init_txn_dict(txn)
		saved_txn = self.get_txn(txn)
		txn['requests'] = 1

		if saved_txn is None:
			self.begin_txn(txn)

		elif saved_txn['Calling-Station-Id'] != txn['Calling-Station-Id']:
			duration = txn['time'] - saved_txn['start_time']
			print 'Conflicting MAC address %s -> %s; (%d); client: %s %s; ORIGINAL: %d requests; %fs ago' % (txn['client'], txn['server'], txn['id'], txn['User-Name'], txn['Calling-Station-Id'],saved_txn['requests'],duration)


			self.begin_txn(txn)
		else:
			duration = txn['time'] - saved_txn['start_time']
			saved_txn['requests'] += 1
			print 'Duplicate request %s -> %s; (%d); client: %s %s; %d requests; first request: %fs ago' % (txn['client'], txn['server'], txn['id'], txn['User-Name'], txn['Calling-Station-Id'],saved_txn['requests'],duration)

	def finish(self,txn):
		saved_txn = self.get_txn(txn)

		if saved_txn is None:
			return None

		else:
			saved_txn['end_time'] = txn['time']
			saved_txn['duration'] = saved_txn['end_time'] - saved_txn['start_time']
			saved_txn['Code'] = txn['Code']

		try:
			del self.txns[txn['server']][txn['client']][txn['port']][txn['id']]
		except KeyError:
			pass


		return saved_txn

	def count(self):
		size = 0
		for server in self.txns:
			for client in self.txns[server]:
				for port in self.txns[server][client]:
					size += len(self.txns[server][client][port])

		return size
					
		

txns = RadiusTransactions()
results = None

# server => client => port => ID
for row in log:
	code = row['Code']
	if row['Protocol'] != 'RADIUS':
		continue

	txn = csv_row_get_txn_info(row)

	if code == 'Access-Request':
		txns.add_request(txn)
	elif code in ['Access-Accept','Access-Reject','Access-Challenge']:
		result = txns.finish(txn)

		if result is None:
			print "%s: invalid txn state client: %s; server: %s" % (txn['Code'],txn['client'],txn['server'])
			continue

		if results is None:
			results = csv.DictWriter(open(RESULT_FILE,'wb'),result.keys())
			results.writeheader()

		results.writerow(result)
	else:
		print "UNHANDLED CODE"
		exit(1)

print "%d unfinished requests" % (txns.count())
