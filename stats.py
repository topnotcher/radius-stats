import csv
LOG_FILE = 'result.csv'

log = csv.DictReader( open(LOG_FILE) )

def update_server_stats(log,stats):
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

def update_stats(log,stats):
	if log['server'] not in stats:
		stats[log['server']] = {'requests':0, 'reject':0, 'challenge':0, 'accept':0, 'time': 0, 'times': [0,0,0,0,0,0]}

	update_server_stats(log,stats[log['server']])

def print_server_stats(stats):
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

	print '\t >25 seconds: %d' % (stats['times'][i])


stats = {}
for row in log:
	update_stats(row,stats)

for server in stats:
	print '-------------------------------------------'
	print 'Statistics for %s' % (server)
	print_server_stats(stats[server])

