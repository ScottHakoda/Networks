import subprocess
import re
import graphviz

def traceroute(url):
    tr = subprocess.Popen(["traceroute", url], stdout=subprocess.PIPE)
    route = []
    while True:
        line = tr.stdout.readline().decode().strip()
        if not line:
            break
        hop = hops(line)
        if hop:
            route.append(hop)
        # read the line based on traceroute's output
    return route

def hops(line):
    if not line or line.strip().startswith('*') or line.lower().startswith('traceroute'):
        return None
    parts = line.split()
    hop_num = parts[0]
    ip_match = re.search(r"\(([\d\.]+)\)", line)
    ip = ip_match.group(1) if ip_match else None
    if not ip:
        return None
    hop = {
        "hop": hop_num,
        "ip": ip
    }
    return hop

def map(dot, url, route):
    prev = None
    for hop in route:
        dot.node(hop['ip'])
        if prev:
            dot.edge(prev, hop['ip'])
        prev = hop['ip']
    dot.node(url)
    dot.edge(prev, url)


def main():
    urls = ["astropy.org", "photutils.readthedocs.io", "ucsc.edu", "ucobservatories.org", "lickobservatory.org", "hilo.hawaii.edu", "keckobservatory.org", "tmt.org", "gemini.edu", "cfht.hawaii.edu", "nso.edu", "cso.caltech.edu", "kpno.noirlab.edu", "subarutelescope.org", "www.nao.ac.jp", "www.ioa.s.u-tokyo.ac.jp", "eso.org", "rmg.co.uk", "saao.ac.za", "sidingspringobservatory.com.au"]
    dot = graphviz.Graph('Internet', strict=True)

    for url in urls:
        print(f'Tracing {url}...')
        route = traceroute(url)
        map(dot, url, route)
    
    dot.render()
    

if __name__ == "__main__":
    main()  


"""
astropy.org
photutils.readthedocs.io
ucsc.edu
ucobservatories.org
lickobservatory.org
hilo.hawaii.edu
keckobservatory.org
tmt.org
gemini.edu
cfht.hawaii.edu
nso.edu
cso.caltech.edu
kpno.noirlab.edu
subarutelescope.org
www.nao.ac.jp
www.ioa.s.u-tokyo.ac.jp
eso.org
rmg.co.uk
saao.ac.za
sidingspringobservatory.com.au
"""