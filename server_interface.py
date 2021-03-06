from flup.server.fcgi import WSGIServer

import calendar
import urlparse
import time
import json
import norse
import os.path
import threading
import Queue

req_queue = Queue.Queue(10000)
res_queue = Queue.Queue(10000)

NUM_REQ_THREADS = 20

auther = None

beg = ""
end = ""

http_codes = {
			'404': '404 Not Found',
			'303': '303 See Other',
			'500': '500 Internal Server Error',
			'503': '503 Service Unavailable'
	}

threezerothree = http_codes['303']
fourzerofour = http_codes['404']
fivezerothree = http_codes['503']
fivehundred = http_codes['500']

text_plain = [('Content-Type', 'text/plain')]

def servcont(environ, start_response):
	start = time.time()
	addr = environ['REMOTE_ADDR']
	path = environ['PATH_INFO']
	try:
		tmp = distribute(environ, start_response, addr, path)
	except Exception, e:
		print e
		end = time.time()
		print time.time(), "\t", addr, "\t", path, "\t", end-start
		start_response(fivezerothree, text_plain)
		return [fivehundred]

	end = time.time()
	print time.time(), "\t", addr, "\t", path, "\t", end-start
	return tmp

def distribute(environ, start_response, addr, path):
	if environ['REQUEST_METHOD'] != 'GET':
		start_response(fourzerofour, text_plain)
		return [fourzerofour]

	if path == '/':
		start_response(fourzerofour, text_plain)
		return [fourzerofour]
	elif path == '/dash.do':
		try:
			norse.TumblrAuth.identities[addr]
		except KeyError, e:
			start_response(threezerothree, [('Content-Type', 'text/plain'),
								('Location', 'login.do')])
			return ["You have to login first. Please go to http://griddlr.com/login.do"]

		return contentrequest(environ, start_response, addr)
	elif path == '/login.do':
		return beginauthuser(environ, start_response, addr)
	elif path == '/callback.do':
		if environ['REDIRECT_STATUS'] == '200':
			return endauthuser(environ, start_response, addr)
		else:
			start_response(fivezerothree, text_plain)
			return [fivezerothree]
	# Default error page
	start_response(fourzerofour, text_plain)
	return [fourzerofour]

def beginauthuser(environ, start_response, addr):
	ident = [addr,None]
	ret = auther.authreq(ident)
	if ret[0]:
		# Redirect the user to tumblr w/ the oauth request token
		start_response(threezerothree, [('Content-Type', 'text/plain'),
							('Location', '%s?oauth_token=%s' % (ret[1], ret[2])),
							('Authorization', ret[2])
							])
		return ['Success']
	else:
		start_response(fivezerothree, text_plain)
		return ret[1]

def endauthuser(environ, start_response, addr):
	response = dict(urlparse.parse_qsl(environ['QUERY_STRING']))
	
	ident = [addr,response['oauth_verifier']]
	auther.authconf(ident)
	start_response(threezerothree, [('Content-Type', 'text/plain'),
		            ('Location', '/')])
	return ['Success']
	
def contentrequest(environ, start_response, addr):
	ident = [addr]
	env = urlparse.parse_qs(environ['QUERY_STRING'])

	try:
		first = int(env['first'][0])
	except Exception, e:
		first = 0

	try:
		off = int(env['off'][0])
	except Exception, e:
		off=0

	clist = []
	resp = []
	rlist = []

	
	num = 40
	for i in xrange(off, off+num, 10):
		req_queue.put([ident, i, 10])

	for i in xrange(num/10):
		res = res_queue.get()
		if res != 'fail':
			resp.extend(res)
		res_queue.task_done()


	for i in resp:
		idv = i['id']
		if idv > first:
			first = idv
	
	
	first_count = False
	for i in resp:
		if i['id'] == first:
			if first_count:
				break
			first_count = True
		rlist.append(i)

	sorted(rlist, key=lambda x: x['id'])

				#var content = first + data[i].caption + second + data[i].hires + third + data[i].notes + fourth + data[i].numnotes + fifth + data[i].perma + sixth + data[i].date + seventh + data[i].img + eigth + data[i].caption + ninth

	for i in rlist:
		for j in i['photos']:
			month = time.gmtime(i['timestamp']).tm_mon
			month = calendar.month_name[month] + ' ' + str(month)
			post = dict([('id', i['id']),
				('perma', i['post_url']),
				('caption', j['caption']),
				('numnotes', i['note_count']),
				('date', month),
				('hires', j['original_size']['url'])
				])

			for k in j['alt_sizes']:
				if k['width'] == 400:
					post['img'] = k['url']
					break
				
			else:
				post['img'] = post['hires']
			clist.append(post)
	
	content = [json.dumps(clist)]
	
	start_response('200 OK', [('Content-Type', 'application/json')])
	return content

class tumblrthread(threading.Thread):
	TA = norse.TumblrAuth()
	uri = 'http://api.tumblr.com/v2/user/dashboard?type=photo&offset=%s&limit=%s&notes_info=True' 

	def run(self):
		while True:
				req = req_queue.get(True)
				response = self.TA.signreq(req[0], self.uri % (str(req[1]),str(req[2])))
				try:
					parsed = json.loads(str(response))
					parsedrp = parsed['response']['posts']

					res_queue.put(parsedrp)
				except Exception, e:
					res_queue.put('fail')

				req_queue.task_done()
	

if __name__ == '__main__':
	from flup.server.fcgi import WSGIServer
	auther = norse.TumblrAuth()

	for i in range(20):
		t = tumblrthread()
		t.setDaemon(True)
		t.start()

	WSGIServer(servcont, umask=0, bindAddress = '/tmp/fcgi.sock').run()
