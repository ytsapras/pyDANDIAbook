# -*- coding: utf-8 -*-
"""
Created on Thu Mar 21 13:49:31 2019

@author: rstreet
"""
import numpy as np
from astropy.table import Table, Column

class StarMatchIndex:

    def __init__(self):

        self.cat1_index = []
        self.cat1_ra = []
        self.cat1_dec = []
        self.cat1_x = []
        self.cat1_y = []
        self.cat2_index = []
        self.cat2_ra = []
        self.cat2_dec = []
        self.cat2_x = []
        self.cat2_y = []
        self.separation = []
        self.n_match = 0

    def add_match(self,params, log=None, verbose=False, replace_worse_matches=True):

        add_star = True

        if replace_worse_matches:
            add_star = self.remove_worse_matches(params,log=log)

        if add_star:
            for key, value in params.items():

                l = getattr(self,key)

                l.append(value)

                setattr(self,key,l)

            self.n_match += 1

            if log!=None:
                log.info('Star '+str(params['cat1_index'])+'='+str(params['cat2_index'])+' added to matched stars index')

        return add_star

    def check_for_duplicates(self,params, log=None):

        duplicates = {'cat1_index': [], 'cat2_index': []}

        if params['cat1_index'] in self.cat1_index:
            idx = self.cat1_index.index(params['cat1_index'])
            duplicates['cat1_index'].append(idx)

        if params['cat2_index'] in self.cat2_index:
            idx = self.cat2_index.index(params['cat2_index'])
            duplicates['cat2_index'].append(idx)

        if log!=None:
            log.info('Found '+str(len(duplicates['cat1_index']))+' duplicates in the cat1_index with the input star already in the match index at array entries: ')
            log.info(repr(duplicates['cat1_index']))
            log.info('Found '+str(len(duplicates['cat2_index']))+' duplicates in the cat2_index with the input star already in the match index at array entries: ')
            log.info(repr(duplicates['cat2_index']))

        if len(duplicates['cat1_index']) > 2:
            raise IOError('Several duplicate entries in matched_stars cat1_index: '+repr(duplicates))
        if len(duplicates['cat2_index']) > 2:
            raise IOError('Several duplicate entries in matched_stars cat2_index: '+repr(duplicates))

        return duplicates

    def remove_worse_matches(self, params, log=None):
        """Method to review the current matched_stars index to check that
        no closer matches for the current stars have already been identified.
        If worse matches are in the index, they are removed, and this method
        returns add_star=True.  If better existing
        matches are found, this method returns add_star = False"""

        add_star = True
        if params['cat1_index'] in self.cat1_index:
            idx = self.cat1_index.index(params['cat1_index'])

            if params['separation'] < self.separation[idx]:
                self.remove_match(idx,log=log)

            else:
                add_star = False
                if log!=None:
                    log.info('Star proposed for match index duplicates a closer-matching star already in the index.  Match rejected.')

        if add_star:
            if params['cat2_index'] in self.cat2_index:
                idx = self.cat2_index.index(params['cat2_index'])

                if params['separation'] < self.separation[idx]:
                    self.remove_match(idx,log=log)

                else:
                    add_star = False
                    if log!=None:
                        log.info('Star proposed for match index duplicates a closer-matching star already in the index.  Match rejected.')

        return add_star

    def remove_match(self,entry_index, log=None):

        def pop_entry(attribute,index):

            l = getattr(self,attribute)

            try:
                tmp = l.pop(index)
            except IndexError:
                pass

            setattr(self,attribute,l)

        pop_entry('cat1_index',entry_index)
        pop_entry('cat1_ra',entry_index)
        pop_entry('cat1_dec',entry_index)
        pop_entry('cat1_x',entry_index)
        pop_entry('cat1_y',entry_index)

        pop_entry('cat2_index',entry_index)
        pop_entry('cat2_ra',entry_index)
        pop_entry('cat2_dec',entry_index)
        pop_entry('cat2_x',entry_index)
        pop_entry('cat2_y',entry_index)

        pop_entry('separation',entry_index)

        self.n_match -= 1

        if log!=None:
            log.info('Removed star entry '+str(entry_index)+' from matched stars index')

    def summary(self,units='deg'):

        output = 'Summary of '+str(self.n_match)+' stars: \n'

        for j in range(0,self.n_match,1):

            if units=='deg':

                output += 'Catalog 1 star '+str(self.cat1_index[j])+' at ('+\
                    str(self.cat1_ra[j])+', '+str(self.cat1_dec[j])+\
                    ') matches Catalog 2 star '+str(self.cat2_index[j])+' at ('+\
                    str(self.cat2_ra[j])+', '+str(self.cat2_dec[j])+\
                    '), separation '+str(self.separation[j])+' '+units+'\n'

            elif units=='pixel':

                output += 'Catalog 1 star '+str(self.cat1_index[j])+' at ('+\
                    str(self.cat1_x[j])+', '+str(self.cat1_y[j])+\
                    ') matches Catalog 2 star '+str(self.cat2_index[j])+' at ('+\
                    str(self.cat2_x[j])+', '+str(self.cat2_y[j])+\
                    '), separation '+str(self.separation[j])+' '+units+'\n'

            else:
                output += 'Catalog 1 star '+str(self.cat1_index[j])+' at ('+\
                    str(self.cat1_x[j])+', '+str(self.cat1_y[j])+\
                    ') matches Catalog 2 star '+str(self.cat2_index[j])+' at ('+\
                    str(self.cat2_x[j])+', '+str(self.cat2_y[j])+\
                    '), separation '+str(self.separation[j])+' '+units+'\n'
                output += 'Catalog 1 star '+str(self.cat1_index[j])+' at ('+\
                    str(self.cat1_ra[j])+', '+str(self.cat1_dec[j])+\
                    ') matches Catalog 2 star '+str(self.cat2_index[j])+' at ('+\
                    str(self.cat2_ra[j])+', '+str(self.cat2_dec[j])+\
                    '), separation '+str(self.separation[j])+' '+units+'\n'

        return output

    def summarize_last(self,units='deg'):

        j = self.n_match - 1
        print('SUMMARIZE_LAST: ',self.n_match)
        print('Cat 1 index: ',self.cat1_index)
        print('Cat 2 index: ',self.cat2_index)
        print('Cat 1 ra: ',self.cat1_ra)
        print('Cat 1 dec: ',self.cat1_dec)
        print('Cat 1 x: ',self.cat1_x)
        print('Cat 1 y: ',self.cat1_y)
        print('Cat 2 ra: ',self.cat2_ra)
        print('Cat 2 dec: ',self.cat2_dec)
        print('Cat 2 x: ',self.cat2_x)
        print('Cat 2 y: ',self.cat2_y)
        print('Separation: ',self.separation)
        print('Star last index: ',j)

        output = 'Catalog 1 star '+str(self.cat1_index[j])+' at RA,Dec=('+\
                        str(self.cat1_ra[j])+', '+str(self.cat1_dec[j])+'), x,y=('+\
                        str(self.cat1_x[j])+', '+str(self.cat1_y[j])+\
                        ') matches Catalog 2 star '+str(self.cat2_index[j])+' at RA,Dec=('+\
                        str(self.cat2_ra[j])+', '+str(self.cat2_dec[j])+'), x,y=('+\
                        str(self.cat2_x[j])+', '+str(self.cat2_y[j])+\
                        '), separation '+str(self.separation[j])+' '+units+'\n'

        return output

    def find_star_match_index(self, catalog_index, cat2_star_id):
        """Method to find the array index of a star entry in the matched stars list,
        based on it's star ID number from either catalog.

        Inputs:
        :param str catalog_index: Name of catalog index attribute to search
                                    one of {cat1_index, cat2_index}
        :param int cat2_star_id: Star ID index to search for

        Outputs:
        :param int idx: Array index of star or -1 if not found
        """

        catalog_star_index = getattr(self,catalog_index)

        try:
            idx = catalog_star_index.index(cat2_star_id)
        except ValueError:
            idx = -1

        return idx

    def output_match_list(self, file_path):

        f = open(file_path,'w')
        f.write('Total stars matched: '+str(self.n_match)+'\n')
        f.write('# CAT1_INDEX  CAT1_X  CAT1_Y  CAT1_RA  CAT1_DEC  CAT2_INDEX  CAT2_X  CAT2_Y  CAT2_RA  CAT2_DEC  SEP[deg]\n')
        for j in range(0,self.n_match,1):
            f.write(str(self.cat1_index[j])+' '+\
                    str(self.cat1_ra[j])+' '+str(self.cat1_dec[j])+'  '+\
                    str(self.cat1_x[j])+' '+str(self.cat1_y[j])+\
                    ' '+str(self.cat2_index[j])+' '+\
                    str(self.cat2_ra[j])+', '+str(self.cat2_dec[j])+' '+\
                    str(self.cat2_x[j])+', '+str(self.cat2_y[j])+\
                    '  '+str(self.separation[j])+'\n')
        f.close()

    def output_as_table(self):
        table = Table( [ Column(name='dataset_star_id', data = np.array(self.cat2_index), dtype='int'),
                              Column(name='dataset_ra', data = np.array(self.cat2_ra), dtype='float'),
                              Column(name='dataset_dec', data = np.array(self.cat2_dec), dtype='float'),
                              Column(name='dataset_x', data = np.array(self.cat2_x), dtype='float'),
                              Column(name='dataset_y', data = np.array(self.cat2_y), dtype='float'),
                              Column(name='field_star_id', data = np.array(self.cat1_index), dtype='int'),
                              Column(name='field_ra', data = np.array(self.cat1_ra), dtype='float'),
                              Column(name='field_dec', data = np.array(self.cat1_dec), dtype='float'),
                              Column(name='field_x', data = np.array(self.cat1_x), dtype='float'),
                              Column(name='field_y', data = np.array(self.cat1_y), dtype='float'),
                              Column(name='separation', data = np.array(self.separation), dtype='float') ] )
        return table

    def find_starlist_match_ids(self, catalog_index, star_ids, log,
                                verbose=False, expand_star_ids = False):
        """Method to find the array index of a star entry in the matched stars list,
        based on it's star ID number from either catalog.

        Inputs:
        :param str catalog_index: Name of catalog index attribute to search
                                    one of {cat1_index, cat2_index}
        :param list star_ids: Star ID indices to search for (from catalog_index)

        Outputs:
        :param array idx: Array index of star or -1 if not found
        """

        star_ids = np.array(star_ids)
        if verbose:
            log.info('Searching for '+str(len(star_ids))+' stars in index '+catalog_index)

        search_catalog_index = np.array( getattr(self,catalog_index) )
        if catalog_index == 'cat1_index':
            result_catalog = 'cat2_index'
        else:
            result_catalog = 'cat1_index'

        result_catalog_index = np.array( getattr(self,result_catalog) )

        # Rows in the list of star IDs where the star is present in the catalog
        present = np.isin(star_ids, search_catalog_index)

        if verbose:
            log.info('Stars present in search index: '+str(len(np.where(present)[0])))
            log.info('Length of present array='+str(len(present))+\
                ' should equal list of input star IDs='+str(len(star_ids)))

        # Indicies in the matched index of the sought-after stars
        entries = np.where(np.isin(search_catalog_index, star_ids))[0]

        if verbose:
            log.info('Identified '+str(len(entries))+\
                    ' array entries in the search index for these stars')

        # Check for any non-unique entries:
        (unique_search_ids, unique_search_index) = np.unique(search_catalog_index,return_index=True)
        non_unique_search_ids = np.delete(search_catalog_index, unique_search_index)
        non_unique_search_index = np.delete(np.arange(0,len(search_catalog_index),1), unique_search_index)

        if len(non_unique_search_ids) > 0:
            log.info('Found '+str(len(non_unique_search_ids))+' non-unique entries in the matched_stars index: '+repr(non_unique_search_ids))
            log.info('at array positions in the matched_stars index: '+repr(non_unique_search_index))

            raise IOError('Found duplicate entries in the matched_stars index.  Cannot store photometry reliably.')
        else:
            log.info('Found no duplicates in the matched_stars index')

        result_star_index = np.zeros(len(star_ids), dtype='int')
        result_star_index.fill(-1)

        result_star_index[present] = result_catalog_index[entries]

        return star_ids, result_star_index


    def reject_outliers(self,inliers, log=None):

        self.cat1_index = np.array(self.cat1_index)[inliers].tolist()
        self.cat1_ra = np.array(self.cat1_ra)[inliers].tolist()
        self.cat1_dec = np.array(self.cat1_dec)[inliers].tolist()
        self.cat1_x = np.array(self.cat1_x)[inliers].tolist()
        self.cat1_y = np.array(self.cat1_y)[inliers].tolist()

        self.cat2_index = np.array(self.cat2_index)[inliers].tolist()
        self.cat2_ra = np.array(self.cat2_ra)[inliers].tolist()
        self.cat2_dec = np.array(self.cat2_dec)[inliers].tolist()
        self.cat2_x = np.array(self.cat2_x)[inliers].tolist()
        self.cat2_y = np.array(self.cat2_y)[inliers].tolist()

        #self.separation = np.array(self.separation)[inliers].tolist()
        self.n_match = len(self.cat2_x)

def transfer_main_catalog_indices(matched_stars, sub_detected_sources, sub_catalog_sources,
                                full_detected_sources, full_catalog_sources, log):

    log.info('Transferring the indices for matched stars from the full catalog array')

    new_matched_stars = StarMatchIndex()

    for j in range(0,len(matched_stars.cat1_index),1):

        # Array indices of matched star in the sub-catalogs
        sdet = matched_stars.cat1_index[j]
        scat = matched_stars.cat2_index[j]
        # Entries of the corresponding star from the full catalogs
        detected_star = sub_detected_sources[sdet]
        sub_catalog_star = sub_catalog_sources[scat]

        jdx = np.where(full_catalog_sources['source_id'] == sub_catalog_star['source_id'])[0][0]
        catalog_star = full_catalog_sources[jdx]

        p = {'cat1_index': detected_star['index']-1, # Convert star number->array index
             'cat1_ra': detected_star['ra'],
             'cat1_dec': detected_star['dec'],
             'cat1_x': detected_star['x'],
             'cat1_y': detected_star['y'],
             'cat2_index': jdx,
             'cat2_ra': catalog_star['ra'],
             'cat2_dec': catalog_star['dec'], \
             'cat2_x': catalog_star['x'],
             'cat2_y': catalog_star['y'], \
             'separation': matched_stars.separation[j]}

        new_matched_stars.add_match(p)

    return new_matched_stars
