#!/usr/bin/env python

import os #for edit()
import csv
import ast
import json
from chirp.chirp_common import Memory, DMRMemory, parse_freq 
from collections import Counter

class DMRDump( object ):
    # add http://www.nerepeaters.com/NERepeaters.php
    def __init__(self):
        dd = "datadump.json"
        with open(dd,"r") as datadump:
            self.dmrmarc = json.load( datadump )


    @staticmethod
    def parse_offset( offset ):
        duplex = ""
        direction = float(offset) > 0
        offset = parse_freq( offset )
        print("Direction: ", direction)
        if abs(offset) == 5e6 or abs(offset) == 6e5 or abs(offset) == 5e5 or not direction:
            #TODO better way? anything <100mhz maybe?
            duplex = "+" if direction else "-";
            offset = abs(offset)
        else:
            print("SPLIT: ", offset)
        return duplex, offset

    @staticmethod
    def repeater_to_memory( r ):
        mem = DMRMemory()
        mem.comment = r['locator'] + ':' +r['city']+ "," + r['state'] + "," + r['country']
        mem.freq = parse_freq( r['frequency'] )
        mem.colorcode = int(r['color_code']) #check this, it's not coming through
        mem.mode = "DMR"
        mem.duplex, mem.offset = DMRDump.parse_offset(r['offset'])
        mem.name = r['callsign']
        mem.empty = False
        return mem
    
    def rxgroups_and_repeaters_to_memories( self, radio, rxgroups, repeaters, many=False ):
        """
            Feed me the current radio, a tuple of rxgroups for TS1 and TS2, and a repeater.
            Rxgroups must be a resolvable reference to a currently loaded rxgroup (int index or string name).

            Each rxgroup's first contact id will be used as the txgroup if "many" is set to False.
            If "many" is set to True, a memory will be created for each valid group in the rxgroup.

            These memories for the set of rx/tx groups will then be returned.

            TODO: many is ignored. :(
        """
        def get_rxgroup(rxg):
            try:
                rxg.cidxs[0]
                return rxg
            except AttributeError as e:
                i,c = radio.rxgroups.try_resolve( radio.find_rxgroup_by_name, rxg )
                if not c and i:
                    return self.rxgroups[i]
                elif c:
                    return c
                else:
                    raise ValueError("Bad RXGroup")

        mems = []
        ts1rxg, ts2rxg = rxgroups

        for r in repeaters:
            base = self.repeater_to_memory( r )
            def truncate( s, l, suffix=None ):
                """ Truncate s to l chars if necessary. Append a suffix if one is supplied. """
                if len(s) > l:
                    if suffix:
                        return s[ :l ] + suffix
                    else:
                        return s[ :l ]
                else:
                    return s

            def mem_per_timeslot(base, ts, rxg ):
                r_rxg = get_rxgroup( rxg ) #resolved rxgroup, so we can access elements from it
                t = base.dupe()
                t.timeslot = ts
                t.rxgroup = rxg
                if not many:
                    t.txgroup = r_rxg.cidxs[0]
                else:
                    raise NotImplementedError

                #ideally bank names should remove at least 1 or two elements from the naming so 
                # we can still have a full name based on the current zone and channel
                try:
                    txgroupname = radio.contacts[t.txgroup].name
                except:
                    txgroupname = t.txgroup
                t.name = "%d-%s"%( 
                        ts,
                        truncate( r['city'], 13).capitalize(),
                        # truncate( txgroupname, 5 ),
                        # truncate( t.name, 5).upper(), 
                        )
                return t

            t1 = mem_per_timeslot( base, 1, ts1rxg )
            print(t1)
            t2 = mem_per_timeslot( base, 2, ts2rxg )
            print(t2)

            mems.append(t1)
            mems.append(t2)
        
        print("Created %d mems"%(len(mems)))
        return mems
        


    def find(self,**kwargs):
        rs = []
        for r in self.dmrmarc['repeaters']:
            addthis=True
            for k,v in kwargs.items():
                if r[k] != v:
                    addthis = False
            if addthis:
                rs.append(r)
        return rs

    def fieldcount(self,*args, **kwargs):
        returnme = {}
        for field in args:
            returnme[field] = Counter()
            for r in self.dmrmarc['repeaters']:
                addthis=True
                for k,v in kwargs.items():
                    if r[k] != v:
                        addthis = False
                if addthis:
                    returnme[ field ][ r[ field ] ] += 1
        return returnme

class DMRContact( object ):
    def __init__(self, contact=None, name=None, callid=None, flags=None):
        self._contact = contact
        self.name = ''
        self.callid = -1
        self.flags = -1
        if self._contact:
            self.name = self._contact.name
            self.callid = self._contact.callid
            self.flags = self._contact.flags
        if name:
            self.name = name
        if callid:
            self.callid = callid
        if flags:
            self.flags = flags

    def __getitem__(self, item):
        return getattr(self, item)

    def isempty(self):
        raise NotImplementedError

    def __setitem__(self, item, value):
        return setattr(self, item, value)

    def __str__(self):
        return "DMRContact %s %s 0x%x"%( self.name, str(self.callid), self.flags)

    def out(self):
        return {"name":self.name, "callid":self.callid, "flags":self.flags}



class DMRRXGroup( object ):
    def __init__(self, group=None, name=None, cidxs=None):
        self._group = group
        self.cidxs = []
        self.name = ''
        if self._group:
            self.name = self._group.name
            self.cidxs = self._group.contactidxs
        if name:
            self.name = name
        if cidxs:
            self.cidxs = cidxs

    def __getitem__(self, item):
        return getattr(self, item)

    def __setitem__(self, item, value):
        return setattr(self, item, value)

    def isempty(self):
        raise NotImplementedError

    def out(self):
        return {"name":self.name, "contactidxs": self.cidxs}

    def add(self, cid):
        self.cidxs.append(cidx)

    def rem(self, cid):
        self.cidxs.remove(cidx)

    def __str__(self):
        return "DMRRXGroup %s len(%d) %s" %( self.name, len(self.cidxs), [x for x in self.cidxs if x != 0 ] )

def builddict( o, names ):
    d = {}
    for n in names:
        try:
            d[n] = o[n]
        except:
            d[n] = getattr( o, n )
    return d

class DMRContactList( object ):
    fieldnames = ["name","callid","flags"]
    def __init__(self, cl=None ):
        self.cl = cl
        if self.cl is None:
            self.cl = []

    def add(self, c ):
        self.cl.append(c)

    def __getitem__(self, item):
        return self.cl[item] 

    def __setitem__(self, item, value):
        self.cl[item]  = value
        return self.cl[item]

    def __len__(self):
        return len(self.cl)
    
    def to_csv(self, fh):
        w = csv.DictWriter( fh, fieldnames=self.fieldnames)
        for each in self.cl:
            w.writerow( builddict( each, self.fieldnames)  )

    def find( self, **kwargs ):
        these = []
        for each in self.cl:
            addthis=True
            for k,v in kwargs.items():
                if each[k] != v:
                    addthis = False
                else:
                    pass #print("Match on %s, %s"%(k,v))
            if addthis:
                these.append(each)
        return these

    def set( self, selectme, setme):
        these = self.find( **selectme )
        for each in these:
            for k,v in setme.items():
                print("Setting %s to %s in %s"%(k,v,each))
                each[k] = v


    @classmethod
    def from_csv(cls, radio, fh ):
        me = cls()
        r = csv.DictReader( fh, fieldnames=me.fieldnames, delimiter="," )
        for c in r:
            # print(c)
            name = c['name']
            callid = int(c['callid'])
            flags = int(c['flags'])
            ce = radio.contact( None, name, callid, flags)
            # print(ce)
            me.cl.append( ce )
        return me

class DMRRXGroupList( object ):
    fieldnames = ["name","cidxs"]
    def __init__(self, gl=None ):
        self.gl = gl
        if self.gl is None:
            self.gl = []
    def __len__(self):
        return len(self.gl)

    def add(self, g ):
        self.gl.append(g)

    def try_resolve(self, converterfn, val):
        try:
           return int( val ), None
        except ValueError as e:
            pass
            print("try_resolve",e)
        except Exception as e:
            print(e)
            # raise(e)
        returnme = converterfn(val)
        print("try_resolve", val, returnme)
        return returnme

    def resolve(self, radio):
        for rxg in self.gl:
            g = rxg.cidxs
            newg = []
            for c in g:
                idx, contact = self.try_resolve( radio.find_contact_by_name, c)
                if contact == None and idx == None:
                    idx = 0
                newg.append(idx)
            rxg.cidxs = newg


    def find( self, **kwargs ):
        these = []
        for each in self.gl:
            addthis=True
            for k, v in kwargs.items():
                if each[ k ] != v:
                    addthis = False
                else:
                    pass #print("Match on %s, %s"%(k,v))
            if addthis:
                these.append( each )
        return these
        
    def set( self, selectme, setme):
        these = self.find( **selectme )
        for each in these:
            for k,v in setme.items():
                print("Setting %s to %s in %s"%(k,v,each))
                each[k] = v

    def __getitem__(self, item):
        return self.gl[item]

    def __setitem__(self, item, value):
        self.gl[item] = value
        return self.gl[item]

    def to_csv(self, fh):
        w = csv.DictWriter( fh, fieldnames=self.fieldnames, delimiter=",")
        for each in self.gl:
            # w.writerow( builddict( each, self.fieldnames)  )
            w.writerow( {'name':each['name'], 'cidxs':each['cidxs'] })

    @classmethod
    def from_csv(cls, radio, fh ):
        me = cls()
        r = csv.DictReader( fh, fieldnames=me.fieldnames, delimiter="," )
        for rx in r:
            rxg = radio.rxgroup( None, rx['name'], ast.literal_eval( rx['cidxs'] ) )
            me.gl.append( rxg )
        return me

        # TODO use UUIDs per row to keep track of contacts and such before building and sending to radio?



class DMRRadio( object ):
    rxgroupsfn = "_rxgroups.csv"
    contactsfn = "_contacts.csv"
    memoriesfn = "_memories.csv"

    rxgrouplist = DMRRXGroupList
    rxgroup = DMRRXGroup
    contactlist = DMRContactList
    contact = DMRContact


    def fix(self):
        print("DMR fix")
        raise NotImplementedError

    def unfix(self):
        print("DMR unfix")
        raise NotImplementedError

    def to_csv(self, basename):
        print("radio to_csv")
        with open( basename + self.rxgroupsfn,"wb") as fh:
            self.rxgroups.to_csv(fh)
        with open( basename + self.contactsfn,"wb") as fh:
            self.contacts.to_csv(fh)
        with open( basename + self.memoriesfn, "wb") as fh:
            c = csv.writer( fh)
            low,high = self.get_features().memory_bounds
            i=low
            while i <= high:
                mem = self.get_memory(i)
                # print(mem)
                c.writerow( mem.to_csv() )
                i+=1
    
    # @classmethod
    def from_csv(cls, basename):
        print('from_csv', basename)
        m = cls
        # m = cls(None)
        # m.load( radio_image_file )
        with open( basename + m.rxgroupsfn, "rb") as fh:
            m.rxgroups = m.rxgrouplist.from_csv(m, fh)
        with open( basename + m.contactsfn, "rb") as fh:
            m.contacts = m.contactlist.from_csv(m, fh)
        with open( basename + m.memoriesfn, "rb") as fh:
            for line in fh:
                mem = Memory._from_csv( line )
                # print(mem)
                m.set_memory(mem)
            
        return m

    def add_memories_from_repeater(self, dmrdump, **kwargs):
        rs = dmrdump.find( **kwargs )
        for r in rs:
            m = dmrdump.repeater_to_memory( r )
            print(m)
            i = self.add_memory(m)
            print("added m to i %d"%i,m)

    def add_memory(self, mem):
        l,h = self.get_features().memory_bounds
        for i in xrange(l, h+1):
            m = self.get_memory(i)
            if m.empty:
                print("Empty:",i,m)
                mem.number = i
                self.set_memory(mem)
                return i

        raise Exception("No more memory slots left! Clear a bunch out and try again.")

    def add_memories(self, mems):
        for m in mems:
            self.add_memory(m)

    def add_rxgroup(self, rxgroup):
        l,h = (1,200) #TODO radio needs to have this feature too, rxgroup sizes
        for i in xrange(l, h+1):
            m = self.get_memory(i)
            if m.empty:
                self.set_memory(mem)
                return i

    def add_contact( self, contact):
        l,h = (0,999) #TODO radio needs to have this feature too, contact sizes
        for i in xrange(l, h+1):
            c = self.contacts[i]
            if c.isempty():
                self.contacts[i] = contact
                return i

    def find_contact_by_name( self, name ):
        print("Finding contact with name: ", name)
        idx=0
        for c in self.contacts:
            if c.name.lower() == name.lower():
                return (idx+1,c)
            idx+=1
        return None, None

    def find_rxgroup_by_name( self, name ):
        print("Finding rxgroup with name: ", name)
        idx=0
        for r in self.rxgroups:
            if r.name == name:
                return (idx+1,r)
            idx+=1
        return None, None
    
