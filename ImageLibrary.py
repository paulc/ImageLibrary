#!/usr/bin/env python

from __future__ import print_function

import errno,json,os,os.path,re,hashlib,shutil,sys
import exifread

date_re = re.compile('(?P<y>(?:20|19)\d\d)[:-]?(?P<m>[01]\d)[:-]?(?P<d>[0-3]\d)')
time_re = re.compile('(?P<h>[012]\d):?(?P<m>[0-5]\d):?(?P<s>[0-5]\d)')

def progress(n=100):
    count = [0]
    def f():
        count[0] += 1
        if not count[0] % n:
            sys.stderr.write('.')
            sys.stderr.flush()
    return f

class ImageLibrary(object):

    def __init__(self,exts=None,minsize=0,exclude=None):
        self.images = {}
        self.exts = exts or ['jpg','JPG','jpeg','JPEG']
        self.minsize = minsize
        self.exclude = exclude or ['Thumbnails','_face','modelresources']

    def scan(self,d):
        def filter(p):
            if os.path.islink(p):
                return True
            if not any([p.endswith(x) for x in self.exts]):
                return True
            if any([ x in p for x in self.exclude]):
                return True
            if os.stat(p).st_size < self.minsize:
                return True
            return False
        sys.stderr.write("Scanning %s: " % d)
        sys.stderr.flush()
        dots = progress()
        for (root,dirs,files) in os.walk(d):
            for f in files:
                p = os.path.join(root,f)
                if filter(p):
                    continue
                path = os.path.abspath(p)
                event = self.get_event(path)
                with open(path,'rb') as image:
                    md5 = hashlib.md5(image.read()).hexdigest()
                if md5 in self.images:
                    if path not in self.images[md5]['path']:
                        self.images[md5]['path'].append(path)
                    if not self.images[md5]['event']:
                        self.images[md5]['event'] = event
                else:
                    self.images[md5] = {'date':self.get_date(path),'event':event,'path':[path],'size':os.stat(path).st_size}
                dots()
        print()


    def get_date_from_name(self,path):
        date = None
        name = os.path.split(path)[1]
        match = date_re.search(name)
        if match:
            (y,m,d) = match.groups()
            try:
                (hh,mm,ss) = time_re.search(name[match.end():]).groups()
            except AttributeError:
                (hh,mm,ss) = ('00','00','00')
            date = "%s:%s:%s %s:%s:%s" % (y,m,d,hh,mm,ss)
        return date

    def get_date_from_exif(self,path):
        date = None
        try:
            with open(path,'rb') as f:
                date = exifread.process_file(f,stop_tag='EXIF DateTimeOriginal',details=False)['EXIF DateTimeOriginal'].values
        except (KeyError,OSError):
            pass
        return date

    def get_date(self,path):
        date = get_date_from_exif(path)
        if not date:
            date = get_date_from_name(path)
        return date
        

    def get_event(self,path):
        s = path.split(os.path.sep)
        if 'Masters' in s or 'Originals' in s or 'Previews' in s:
            return s[-2]
        return None

    def create_path(self,i):
        # Prefer 'original' filenames if available
        paths = [ x for x in i['path'] if 'Masters' in x or 'Originals' in x ] or i['path']
        _,name = os.path.split(paths[0])
        if i['event']:
            f = "%s - %s" % (i['event'],name)
        else:
            f = name
        try:
            y,m,_ = i['date'].split(':',2)
            return os.path.join(y,m,f)
        except (AttributeError,ValueError):
            return os.path.join('Unknown',f)

    def copy_image(self,k,basepath):
        try:
            i = self.images[k]
            src = i['path'][0]
            dest = os.path.join(basepath,self.create_path(i)).encode('ascii',errors='ignore')
            dir,name = os.path.split(dest)
            try:
                os.makedirs(dir)
            except OSError as e:
                if e.errno != errno.EEXIST:
                    raise
            root,ext = os.path.splitext(dest)
            n = 0
            while os.path.exists(root+ext):
                with open(root+ext,'rb') as orig:
                    md5 = hashlib.md5(orig.read()).hexdigest()
                    if md5 == k:
                        print("Skipping:",src.encode('ascii',errors='ignore').decode(),"-->",(root+ext).decode())
                        return
                n += 1
                root = os.path.splitext(dest)[0] + ("-%d" % n).encode()
            print("Copying:",src.encode('ascii',errors='ignore').decode(),"-->",(root+ext).decode())
            shutil.copyfile(src,root+ext)
        except Exception as e:
            import code,traceback
            traceback.print_exc()
            code.interact(local=locals())

    def archive(self,basepath):
        for k in self.images:
            self.copy_image(k,basepath)
        self.save(os.path.join(basepath,"images.json"))

    def save(self,index='images.json'):
        with open(index,'w') as f:
            json.dump(self.images,f,sort_keys=True,indent=2)
    
    def load(self,index='images.json'):
        with open(index) as f:
            self.images = json.load(f)

if __name__ == '__main__':

    import code,pdb,signal

    def handle_pdb(sig,frame):
        pdb.Pdb().set_trace(frame)

    signal.signal(signal.SIGUSR1, handle_pdb)

    import argparse,sys
    a = argparse.ArgumentParser(description="Image Library")
    a.add_argument("--scan",nargs="+",help="Scan dirs")
    a.add_argument("--load",help="Load index from file")
    a.add_argument("--save",help="Save index to file")
    a.add_argument("--copy",help="Copy images to path")
    a.add_argument("--debug",action="store_true",default=False,help="Debug")
    args = a.parse_args()

    images = ImageLibrary()

    if args.load:
        images.load(args.load)
    if args.scan:
        for d in args.scan:
            images.scan(d)
    if args.save:
        images.save(args.save)
    if args.copy:
        images.archive(args.copy)
    if args.debug:
        code.interact(local=locals())

