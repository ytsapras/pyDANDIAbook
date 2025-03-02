# -*- coding: utf-8 -*-
"""
Created on Sat Jul 15 14:08:54 2017

@author: rstreet
"""
from os import path
from astropy.io import fits
from astropy.table import Table
from astropy.table import Column
from astropy.coordinates import SkyCoord
from astropy.utils.exceptions import AstropyWarning
from astropy import units as u
from skimage.transform import AffineTransform

import numpy as np
import collections
import warnings
from pyDANDIA import  logs
from pyDANDIA import match_utils
from pyDANDIA import image_handling

import os
import pathlib

def update_a_dictionary(dictionary, new_key, new_value):
    '''
    Update a namedtuple dictionary with a new key and new value

    :param namedtuple_object dictionary: the dictionary that needs to be updated
    :param string new_key: the new key desired in the new dictionnary
    :param new_value:  the new value associated to the new key.

    :return new_dictionary:  the updated namedtuple dictionary
    :rtype namedtuple dictionary
    '''

    new_keys = dictionary._fields + (new_key,)
    new_dictionary = collections.namedtuple(dictionary.__name__, new_keys)

    for index, key in enumerate(dictionary._fields):
        value = getattr(dictionary, key)

        setattr(new_dictionary, key, value)

    setattr(new_dictionary, new_key, new_value)

    return new_dictionary


class MetaData:
    """Class defining the data structure produced by the pyDANDIA pipeline
    to hold metadata regarding the reduction of a single dataset, including
    reduction configuration parameters, the data inventory and key measured
    parameters from each stage.
    """

    def __init__(self):

        # attributes = [astropy.header,astropy.Table]

        self.data_architecture = [None, None]
        self.reduction_parameters = [None, None]
        self.headers_summary = [None, None]
        self.reduction_status = [None, None]
        self.images_stats = [None, None]

        self.stamps = [None, None]

    def create_metadata_file(self, metadata_directory, metadata_name):
        '''
        Create a metadata fits file from scratch

        :param string metadata_directory: the metadata directory where this file gonna be saved
        :param string metadata_name: the name of the metadata file

        '''
        metadata = fits.HDUList()

        self.create_data_architecture_layer(metadata_directory, metadata_name)
        self.create_reduction_status_layer()

        tbhdu1 = fits.BinTableHDU(self.data_architecture[1], header=self.data_architecture[0])
        tbhdu2 = fits.BinTableHDU(self.reduction_status[1], header=self.reduction_status[0])

        tbhdu1.name = tbhdu1.header['name']
        tbhdu2.name = tbhdu2.header['name']

        metadata.append(tbhdu1)
        metadata.append(tbhdu2)

        metadata.writeto(path.join(metadata_directory, metadata_name), overwrite=True)

    def create_a_new_layer(self, layer_name, data_structure, data_columns=None):
        '''
        Add a new layer to the metadata object

        :param string layer_name: the name associated to the layer
        :param list data_structure: a list containing the
                   [[columns names],[columns format],[columns units]]
        :param array_like data_columns: the content of the astropy.table


        '''

        layer_header = fits.Header()
        layer_header.update({'NAME': layer_name})

        names = data_structure[0]
        try:

            data_format = data_structure[1]
        except:

            data_format = None

        try:

            data_units = data_structure[2]
        except:

            data_units = None

        try:

            data = data_columns

        except:

            data = None

        layer_table = Table(data, names=names, dtype=data_format)

        try:

            for index, key_column in enumerate(layer_table.keys()):
                layer_table[key_column].unit = data_units[index]

        except:

            pass

        layer = [layer_header, layer_table]

        setattr(self, layer_name, layer)

    def remove_metadata_layer(self, layer_name, red_dir, metadata_file):
        """Function to remove a layer from an existing metadata file"""

        if layer_name in dir(self):

            confirm = input('Please confirm that you wish to remove the '+layer_name+\
                            ' table from the metadata.  Y or N: ')
            if 'Y' in str(confirm).upper():
                delattr(self, layer_name)
                self.save_updated_metadata(red_dir,metadata_file)
                print(layer_name+' table removed from '+os.path.join(red_dir, metadata_file))

            else:
                print(layer_name+' NOT removed from metadata')

        else:
            print('No '+layer_name+' table found in metadata object')

    def create_a_new_layer_from_table(self, layer_name, table_data):
        """
        Add a new layer to the metadata object from an astropy Table

        :param string layer_name: the name associated to the layer
        :param list table_data: an astropy-format Table
        """

        layer_header = fits.Header()
        layer_header.update({'NAME': layer_name})

        layer = [layer_header, table_data]

        setattr(self, layer_name, layer)

    def create_data_architecture_layer(self, metadata_directory, metadata_name):
        '''
        Create the data architecture layer, which contains the different directories paths, names etc.

        :param string metadata_directory: the metadata directory where this file will be saved
        :param string metadata_name: the name of the metadata file

        '''
        layer_name = 'data_architecture'
        data_structure = [['METADATA_NAME', 'OUTPUT_DIRECTORY'],
                          ]
        data = [[metadata_name], [metadata_directory]]
        self.create_a_new_layer(layer_name, data_structure, data)

    def create_reduction_parameters_layer(self, names, formats, units, data=None):
        '''
        Create the reduction parameters layer, which contains the information
        in the config.json file

        :param list names: the list of names (string) of the columns
        :param list formats: the list of format (dtype) of the columns
        :param list units: the list of units (string) of the columns
        :param array_like: the data needed to fill the astropy.table

        '''
        name = 'reduction_parameters'

        data_structure = [names,
                          formats,
                          units]

        self.create_a_new_layer(name, data_structure, data)

    def create_psf_dimensions_layer(self, data):
        """Method to create the psf_dimensions table layer in the Metadata,
        based on the information in the config.json file

        :param array_like: the data needed to fill the astropy.table with
                            columns index, psf_factor, psf_radius
                            where psf_factor and psf_radius should have
                            astropy.units of 'pixels'
        """

        existing_layers = dir(self)

        if 'psf_dimensions' not in existing_layers:
            layer_header = fits.Header()
            layer_header.update({'NAME': 'psf_dimensions'})

            table_data = [ Column(name='index', data=data[:,0], unit=None, dtype='int'),
                           Column(name='psf_factor', data=data[:,1], unit=u.pix, dtype='float'),
                           Column(name='psf_radius', data=data[:,2], unit=u.pix, dtype='float') ]

            layer_table = Table(table_data)

            layer = [layer_header, layer_table]

            setattr(self, 'psf_dimensions', layer)

    def get_psf_radius(self):
        """Fetches the value of the PSF radius, which defaults to the largest
        on the list"""

        return self.psf_dimensions[1]['psf_radius'][0]

    def create_headers_summary_layer(self, names, formats, units=None, data=None):
        '''
        Create the headers_summary layer, which contains the information
        in each image header needed by pyDANDIA

        :param list names: the list of names (string) of the columns
        :param list formats: the list of format (dtype) of the columns
        :param list units: the list of units (string) of the columns
        :param array_like: the data need to fill the astropy.table

        '''
        layer_name = 'headers_summary'
        data_structure = [names,
                          formats,
                          units]
        self.create_a_new_layer(layer_name, data_structure, data)

    def expand_headers_summary_layer(self):
        """Function to append additional information to the headers summary,
        both data harvested from the images headers directly, and calculated
        from that data"""

        nimages = len(self.headers_summary[1])
        self.add_column_to_layer('headers_summary', 'HJD', np.zeros(nimages), new_column_format='float',
                                new_column_unit='days')
        self.add_column_to_layer('headers_summary', 'AIRMASS', np.zeros(nimages), new_column_format='float',
                                new_column_unit='')

    def create_reduction_status_layer(self):
        '''
        Create the reduction_status layer, which summarizes the status of the reduction
        for all images vs all stages
        '''
        layer_name = 'reduction_status'
        data_structure = [
            ['IMAGES', 'STAGE_0', 'STAGE_1', 'STAGE_2', 'STAGE_3', 'STAGE_4',
             'STAGE_5', 'STAGE_6', 'STAGE_7'],
            ['S200', 'S10', 'S10', 'S10', 'S10', 'S10', 'S10', 'S10', 'S10'],
        ]

        self.create_a_new_layer(layer_name, data_structure)

    def create_images_stats_layer(self):
        '''
        Create the images_stats layer, which contains the FHWM, sky level,
        correlation parameters, number of stars and
        fraction of saturated pixels for each image.
        This is generated by stage 1 of the pipeline.

        '''

        layer_header = fits.Header()
        layer_header.update({'NAME': 'images_stats'})

        table_data = [ Column(name='IM_NAME', data=np.array([]), unit=None, dtype='S100'),
                       Column(name='SIGMA_X', data=np.array([]), unit=u.pix, dtype='float'),
                       Column(name='SIGMA_Y', data=np.array([]), unit=u.pix, dtype='float'),
                       Column(name='FWHM', data=np.array([]), unit=u.pix, dtype='float'),
                       Column(name='SKY', data=np.array([]), unit=u.adu, dtype='float'),
                       Column(name='CORR_XY', data=np.array([]), unit=None, dtype='float'),
                       Column(name='NSTARS', data=np.array([]), unit=None, dtype='int'),
                       Column(name='FRAC_SAT_PIX', data=np.array([]), unit=None, dtype='float'),
                       Column(name='SYMMETRY', data=np.array([]), unit=None, dtype='float'),
                       Column(name='USE_PHOT', data=np.array([]), unit=None, dtype='int'),
                       Column(name='USE_REF', data=np.array([]), unit=None, dtype='int'),
                     ]

        layer_table = Table(table_data)

        layer = [layer_header, layer_table]

        setattr(self, 'images_stats', layer)

    def create_stamps_layer(self, names, formats, units=None, data=None):
        '''
        Create the stamps layer, which contains the stamps index, and coordinates
        of each frames subdivision

        :param list names: the list of names (string) of the columns
        :param list formats: the list of format (dtype) of the columns
        :param list units: the list of units (string) of the columns
        :param array_like: the data need to fill the astropy.table

        '''
        layer_name = 'stamps'
        data_structure = [names,
                          formats,
                          units]
        self.create_a_new_layer(layer_name, data_structure, data)

    def create_star_catalog_layer(self,data=None,log=None,catalog_source='Gaia'):
        """Function to create the layer in the reduction metadata file
        containing the star catalogue of objects detected within the reference
        image.

        :param array_like: the data need to fill the astropy.table
        """

        layer_name = 'star_catalog'

        if catalog_source == '2MASS':
            names = [ 'star_index',
                    'x_pixel', 'y_pixel',
                    'RA_J2000', 'DEC_J2000',
                    'ref_flux', 'ref_flux_err',
                    'ref_mag', 'ref_mag_err',
                    'J_mag', 'J_mag_err',
                    'H_mag', 'H_mag_err',
                    'Ks_mag', 'Ks_mag_err','null',
                    'psf_star']

            formats = [ 'int',
                       'float', 'float',
                       'float', 'float',
                       'float', 'float',
                       'float', 'float',
                       'float', 'float',
                       'float', 'float',
                       'float', 'float','float',
                       'int'
                       ]

            units = [ None,
                     'pixel', 'pixel',
                     'deg', 'deg',
                     'DN', 'DN',
                     'mag', 'mag',
                     'mag', 'mag',
                     'mag', 'mag',
                     'mag', 'mag',None,
                     None
                     ]

        else:
            names = [ 'star_index',
                    'x_pixel', 'y_pixel',
                    'RA_J2000', 'DEC_J2000',
                    'ref_flux', 'ref_flux_err',
                    'ref_mag', 'ref_mag_err',
                    'gaia_source_id',
                    'ra', 'ra_error',
                    'dec', 'dec_error',
                    'phot_g_mean_flux', 'phot_g_mean_flux_error',
                    'phot_bp_mean_flux','phot_bp_mean_flux_error',
                    'phot_rp_mean_flux', 'phot_rp_mean_flux_error',
                    'psf_star']

            formats = [ 'int',
                       'float', 'float',
                       'float', 'float',
                       'float', 'float',
                       'float', 'float',
                       'int',
                       'float', 'float',
                       'float', 'float',
                       'float', 'float',
                       'float', 'float',
                       'float', 'float',
                       'int'
                       ]

            units = [ None,
                     'pixel', 'pixel',
                     'deg', 'deg',
                     'DN', 'DN',
                     'mag', 'mag',
                     '',
                     'deg', 'deg',
                     'deg', 'deg',
                     "'electron'.s**-1", "'electron'.s**-1",
                     "'electron'.s**-1", "'electron'.s**-1",
                     "'electron'.s**-1", "'electron'.s**-1",
                     None
                     ]

        data_structure = [ names,
                         formats,
                         units]

        self.create_a_new_layer(layer_name, data_structure, data)

        if log != None:

            log.info('Output reference source catalogue to reduction metadata')

    def create_software_layer(self,data,log=None):
        """Function to create a layer in the reduction metadata file
        detailing the software versions used in the reduction"""

        layer_name = 'software'

        names = [ 'stage3_version', 'stage6_version' ]

        formats = ['S50', 'S50']

        units = [None, None]

        data_structure = [ names,
                         formats,
                         units]

        self.create_a_new_layer(layer_name, data_structure, data)

        if log != None:

            log.info('Output software version table to reduction metadata')

    def create_phot_calibration_layer(self,data,covar):
        """Function to create the layer in the reduction metadata file
        containing the star catalogue of objects detected within the reference
        image.

        :param list col_names: column names for table
        :param list formats: column formats
        :param array_like data: the data need to fill the astropy.table
        """

        layer_header = fits.Header()
        layer_header.update({'NAME': 'phot_calib'})

        table_data = [ Column(name='a0', data=np.array([data[0]]), unit=u.mag, dtype='float'),
                       Column(name='a1', data=np.array([data[1]]), unit=None, dtype='float'),
                       Column(name='c0', data=np.array([covar[0,0]]), unit=None, dtype='float'),
                       Column(name='c1', data=np.array([covar[0,1]]), unit=None, dtype='float'),
                       Column(name='c2', data=np.array([covar[1,0]]), unit=None, dtype='float'),
                       Column(name='c3', data=np.array([covar[1,1]]), unit=None, dtype='float') ]

        layer_table = Table(table_data)

        layer = [layer_header, layer_table]

        setattr(self, 'phot_calib', layer)

    def create_matched_stars_layer(self, matched_stars):
        """Method to output a new metadata layer tabulating the crossed-matched identifications between the
        dataset's star IDs and those for the field"""

        table_data = Table( [ Column(name='dataset_star_id', data = np.array(matched_stars.cat2_index), dtype='int'),
                                    Column(name='dataset_ra', data = np.array(matched_stars.cat2_ra), dtype='float'),
                                    Column(name='dataset_dec', data = np.array(matched_stars.cat2_dec), dtype='float'),
                                    Column(name='dataset_x', data = np.array(matched_stars.cat2_x), dtype='float'),
                                    Column(name='dataset_y', data = np.array(matched_stars.cat2_y), dtype='float'),
                              Column(name='field_star_id', data = np.array(matched_stars.cat1_index), dtype='int'),
                                  Column(name='field_ra', data = np.array(matched_stars.cat1_ra), dtype='float'),
                                  Column(name='field_dec', data = np.array(matched_stars.cat1_dec), dtype='float'),
                                  Column(name='field_x', data = np.array(matched_stars.cat1_x), dtype='float'),
                                  Column(name='field_y', data = np.array(matched_stars.cat1_y), dtype='float'),
                        Column(name='separation', data = np.array(matched_stars.separation), dtype='float') ] )

        self.create_a_new_layer_from_table('matched_stars', table_data)

    def create_transform_layer(self, transform):
        """Method to output a new metadata layer to record the transformation between this dataset and the field reference"""

        table_data = Table( [ Column(name='matrix_column0', data = transform.params[:,0], dtype='float'),
                              Column(name='matrix_column1', data = transform.params[:,1], dtype='float'),
                              Column(name='matrix_column2', data = transform.params[:,2], dtype='float') ] )

        self.create_a_new_layer_from_table('transformation', table_data)

    def load_a_layer_from_file(self, metadata_directory, metadata_name, key_layer):
        '''
        Load into the metadata object the layer from the metadata file.

        :param string metadata_directory: the metadata directory where this file will be saved
        :param string metadata_name: the name of the metadata file
        :param string key_layer: the layer to be loaded from the file


        '''

        metadata = fits.open(path.join(metadata_directory,metadata_name), mmap=True)

        layer = metadata[key_layer]

        header = layer.header
        table = Table(layer.data)

        setattr(self, key_layer, [header, table])

    def load_all_metadata(self, metadata_directory, metadata_name):
        '''
        Load into the metadata object all layers contains in the metadata file.

        :param string metadata_directory: the metadata directory where this file will be saved
        :param string metadata_name: the name of the metadata file


        '''

        metadata = fits.open(path.join(metadata_directory, metadata_name), mmap=True)

        all_layers = [i.header['NAME'] for i in metadata[1:]]

        for key_layer in all_layers:

            try:
                self.load_a_layer_from_file(metadata_directory, metadata_name, key_layer)
            except:

                print('No Layer with key name :' + key_layer)

    def load_matched_stars(self):
        """Method to load the matched_stars list"""

        matched_stars = match_utils.StarMatchIndex()

        matched_stars.cat1_index = list(self.matched_stars[1]['field_star_id'])
        matched_stars.cat1_ra = list(self.matched_stars[1]['field_ra'])
        matched_stars.cat1_dec = list(self.matched_stars[1]['field_dec'])
        matched_stars.cat1_x = list(self.matched_stars[1]['field_x'])
        matched_stars.cat1_y = list(self.matched_stars[1]['field_y'])
        matched_stars.cat2_index = list(self.matched_stars[1]['dataset_star_id'])
        matched_stars.cat2_ra = list(self.matched_stars[1]['dataset_ra'])
        matched_stars.cat2_dec = list(self.matched_stars[1]['dataset_dec'])
        matched_stars.cat2_x = list(self.matched_stars[1]['dataset_x'])
        matched_stars.cat2_y = list(self.matched_stars[1]['dataset_y'])
        matched_stars.separation = list(self.matched_stars[1]['separation'])
        matched_stars.n_match = len(matched_stars.cat1_index)

        return matched_stars

    def load_field_dataset_transform(self):
        """Method to load the transformation between the field and the current dataset"""

        matrix = np.zeros( (3,3) )
        matrix[:,0] = self.transformation[1]['matrix_column0']
        matrix[:,1] = self.transformation[1]['matrix_column1']
        matrix[:,2] = self.transformation[1]['matrix_column2']

        transform = AffineTransform(matrix=matrix)

        return transform

    def save_updated_metadata(self, metadata_directory, metadata_name, log=None):
        '''
        Save in the metadata file the updated metadata object (i.e all layers).

        :param string metadata_directory: the metadata directory where this file will be saved
        :param string metadata_name: the name of the metadata file


        '''
        all_layers = self.__dict__.keys()

        for key_layer in all_layers:
            layer = getattr(self, key_layer)
            if layer != [None, None]:
                if log != None:
                    log.info('Writing meta data layer ' + key_layer)
                self.save_a_layer_to_file(metadata_directory, metadata_name, key_layer, log=log)

        if log != None:
            log.info('Stored updated metadata')

    def save_a_layer_to_file(self, metadata_directory, metadata_name,
                             key_layer, log=None):
        '''
        Save in the metadata file the updated layer.

        :param string metadata_directory: the metadata directory where this file will be saved
        :param string metadata_name: the name of the metadata file
        :param string key layer: the name of the layer to be saved

        '''

        layer = getattr(self, key_layer)

        with warnings.catch_warnings():
            warnings.simplefilter('ignore', AstropyWarning)
            update_layer = fits.BinTableHDU(layer[1], header=layer[0])
            update_layer.name = update_layer.header['name']

        try:
            metadata = fits.open(path.join(metadata_directory, metadata_name),
                                 mmap=True)
            try:

                metadata[key_layer] = update_layer

            except:

                metadata.append(update_layer)

            metadata.writeto(path.join(metadata_directory, metadata_name),
                             overwrite=True)

        except IOError:
            if log != None:
                log.info('ERROR: Cannot output metadata to file ' + \
                         path.join(metadata_directory, metadata_name))

    def transform_2D_table_to_dictionary(self, key_layer):
        '''
        Transform a 2D astropy.table to a collection.namedtuple dictionary

        :param string key_layer: the name of the layer to transform to a dictionary

        :return dictionary : a namedutple.dicitonary containing the astropy.table
        :rtype collections.namedtuple
        '''
        layer = getattr(self, key_layer)

        keys = layer[1].keys()

        dictionary = collections.namedtuple(key_layer + '_dictionary', keys)

        for index, key in enumerate(dictionary._fields):
            setattr(dictionary, key, layer[1][key][0])

        return dictionary

    def update_2D_table_with_dictionary(self, key_layer, dictionary):
        '''
        Update a layer using a dictionary

        :param string key_layer: the name of the layer to be saved
        :param collections.namedtuple dictionary: the dictionary that will be
        translated to an astropy.table

        '''
        layer = getattr(self, key_layer)
        column_names = layer[1].keys()

        for index, key in enumerate(dictionary._fields):

            value = getattr(dictionary, key)

            if key in column_names:

                layer[1][key][0] = value

            else:

                layer[1].add_column(Column([value], name=key, dtype=type(value)))

    def add_row_to_layer(self, key_layer, new_row):
        '''
        Add a row to a specific layer

        :param string key_layer: the name of the layer to be saved
        :param list new_row: the list of values which will be appended to the layer

        '''

        layer = getattr(self, key_layer)
        layer_keys = layer[1].keys()

        first_column = layer[1][layer_keys[0]]

        if new_row[0] in first_column:
            #update the row, not creating a new one
            row_index = np.where(new_row[0]==first_column)[0]
            self.update_row_to_layer(key_layer, row_index, new_row)

        else:

            layer[1].add_row(new_row)

    def add_column_to_layer(self, key_layer, new_column_name, new_column_data, new_column_format=None,
                            new_column_unit=None):
        '''
        Add a entire column to a specific layer

        :param string key_layer: the name of the layer to be saved
        :param dtype new_column_name: the name of the new_column
        :param list new_column_data: the data representing the new column added
        :param string new_column_unit: the dunit of the new column

        '''

        layer = getattr(self, key_layer)
        layer_keys = layer[1].keys()

        if new_column_name in layer_keys:

            # update the column, not creating a new one
            self.update_column_to_layer(key_layer, new_column_name, new_column_data)

        else:


            new_column = Column(new_column_data, name=new_column_name.upper(),
                            dtype=new_column_format, unit=new_column_unit)
            layer[1].add_column(new_column)

    def update_row_to_layer(self, key_layer, row_index, new_row):
        '''
        Modify an entire row of the layer

        :param string key_layer: the name of the layer to be saved
        :param int row_index: the index of the line
        :param list new_row: the new line content

        '''

        layer = getattr(self, key_layer)
        layer[1][row_index] = new_row

    def update_column_to_layer(self, key_layer, key_column, new_column):
        '''
        Modify an entire column of the layer

        :param string key_layer: the name of the layer to be saved
        :param string key_column: the name  of the column
        :param list new_column: the new line content

        '''
        layer = getattr(self, key_layer)
        layer[1][key_column] = new_column

    def find_all_images(self, setup, reduction_metadata, images_directory_path=None, log=None,):
        '''
        Find all the images.

        :param object reduction_metadata: the metadata object
        :param string images_directory_path: the directory of the images
        :param boolean verbose: switch to True to have more information

        :return: the list of images (strings)
        :rtype: list
        '''

        try:

            path = reduction_metadata.data_architecture[1]['IMAGES_PATH'][0]

        except:

            if images_directory_path:
                path = images_directory_path

                reduction_metadata.add_column_to_layer('data_architecture', 'images_path', [path])

        try:

            list_of_images = [i.name for i in pathlib.Path(path).iterdir() if ('.fits' in i.name) and ('.gz' not in i.name) and ('.bz2' not in i.name)]

            if list_of_images == []:

                logs.ifverbose(log, setup, 'No images to process. I take a rest :)')

                return None


            else:

                logs.ifverbose(log, setup, 'Found ' + str(len(list_of_images)) + \
                               ' images in this dataset')

                return list_of_images

        except:

            logs.ifverbose(log, setup, 'Something went wrong with the image search!')

            return None

    def find_images_need_to_be_process(self, setup, list_of_images, stage_number=None,
                                       rerun_all=None,process_missing=True,
                                       log=None):
        '''
        This finds the images that need to be processed by the pipeline, i.e not already done.

        :param object reduction_metadata: the metadata object
        :param  list list_of_images: the directory of the images
        :param boolean verbose: switch to True to have more information
        :param boolean process_missing: switch to trigger inclusion of added
                                    images not yet included in the
                                    reduction_status table

        :return: the new images that need to be processed.
        :rtype: list
        '''

        layer = self.reduction_status

        column_name = 'STAGE_'+str(stage_number)
        if rerun_all:
            for name in list_of_images:

                image_row = np.where(layer[1]['IMAGES'] == name)[0]
                self.update_a_cell_to_layer('reduction_status', image_row,column_name,0)


        try:

            if len(layer[1]) == 0:

                new_images = list_of_images

            else:

                new_images = []

                for name in list_of_images:

                    image_row = np.where(layer[1]['IMAGES'] == name)[0]

                    if len(image_row) != 0:

                        if layer[1][image_row[0]][column_name] == '0':
                            logs.ifverbose(log, setup,
                                           name + ' is a new image to process by stage number: ' + str(stage_number))
                            new_images.append(name)

                    else:
                        if process_missing:
                            logs.ifverbose(log, setup,
                                       name + ' is a new image to process by stage number: ' + str(stage_number))
                            new_images.append(name)
                        else:
                            logs.ifverbose(log, setup,
                                       name + ' is a recently-added image not yet ready for processing by stage number: ' + str(stage_number))

        except:
            if log != None:
                log.info('Error in scanning for new images to reduce')

        if log != None:
            log.info('Total of ' + str(len(new_images)) + ' images need reduction')

        if len(new_images) == 0:
            log.info('WARNING: No valid images found to be needing reduction')

        return new_images

    def fetch_image_status(self,stage_number):
        """Method to return a dictionary of the reduction status of all images"""

        layer = self.reduction_status
        image_list = layer[1]['IMAGES'].data
        data = layer[1]['STAGE_'+str(stage_number)].data

        image_stat = {}
        for i in range(0,len(image_list),1):
            image_stat[image_list[i]] = data[i]

        return image_stat

    def update_a_cell_to_layer(self, key_layer, row_index, column_name, new_value):
        '''
        Modify an entire row of the layer

        :param string key_layer: the name of the layer to be saved
        :param int row_index: the index of the line
        :param string the column name: the column name
        :param new value: the new value of the cell

        '''

        layer = getattr(self, key_layer)
        layer[1][column_name][row_index] = new_value

    def update_reduction_metadata_reduction_status(self, new_images, stage_number=0,
        status = '0', log = None):
        '''
        Update the reduction_status layer with all images of the stage set to status

        :param object reduction_metadata: the metadata object
        :param list new_images: list of string with the new image names
        :param int status: status of stage0 reduction for a frame. 0 : not done
                                                                   1 : done
                                                                   -1: do not use
        '''

        layer = self.reduction_status
        number_of_columns = len(layer[1].keys())-1
        if len(layer[1])==0:
            for image in new_images:

                    self.add_row_to_layer('reduction_status',[image]+number_of_columns*['0'])

        else:
            column_name = 'STAGE_'+str(stage_number)
            for image in new_images:

                if image in layer[1]['IMAGES'] :
                    index_image = np.where(layer[1]['IMAGES'] == image)[0][0]
                    self.update_a_cell_to_layer('reduction_status', index_image, column_name, status)
                else:

                    self.add_row_to_layer('reduction_status',[image]+number_of_columns*['0'])

        if log != None:
            log.info('Updated the reduction status layer')


    def update_reduction_metadata_reduction_status_list(self, new_images, status,
                                                    stage_number=0, log = None):
        '''
        Update the reduction_status layer with all images of the stage set to status

        :param object reduction_metadata: the metadata object
        :param list new_images: list of string with the new image names
        :param list status: status of stage0 reduction for all frames. 0 : not done
                                                                       1 : done
                                                                      -1: do not use
        '''

        layer = self.reduction_status
        number_of_columns = len(layer[1].keys())-1
        if len(layer[1])==0:
            for image in new_images:

                    self.add_row_to_layer('reduction_status',[image]+number_of_columns*[0])

        else:
            column_name = 'STAGE_'+str(stage_number)
            for i,image in enumerate(new_images):

                if image in layer[1]['IMAGES'] :
                    index_image = np.where(layer[1]['IMAGES'] == image)[0][0]
                    self.update_a_cell_to_layer('reduction_status', index_image, column_name, status[i])

                    if status[i] == -1:
                        for c in range(stage_number,8,1):
                            self.update_a_cell_to_layer('reduction_status', index_image, 'STAGE_'+str(c), status[i])
                else:

                    self.add_row_to_layer('reduction_status',[image]+number_of_columns*[0])

        if log != None:
            log.info('Updated the reduction status layer')

    def update_reduction_metadata_reduction_status_dict(self, image_status,
                                                    stage_number=0, log = None):
        '''
        Update the reduction_status layer with all images of the stage set to status

        :param object reduction_metadata: the metadata object
        :param list image_status: list of string with the new image names
        :param int stage_number: [optional]
        :param log object: Open log
        '''

        layer = self.reduction_status
        column_name = 'STAGE_'+str(stage_number)

        for image, stat in image_status.items():
                if image in layer[1]['IMAGES'] :
                    index_image = np.where(layer[1]['IMAGES'] == image)[0][0]
                    self.update_a_cell_to_layer('reduction_status', index_image,
                                                column_name, stat)

                    if '-1' in str(stat):
                        for c in range(stage_number,8,1):
                            self.update_a_cell_to_layer('reduction_status',
                                                        index_image,
                                                        'STAGE_'+str(c),
                                                        stat)

                else:
                    raise IOError('Attempt to update the status of an image unknown to the metadata reduction status table: '+image)

        if log != None:
            log.info('Updated the reduction status layer')

    def set_all_reduction_status_to_0(self, log=None):
        '''
            Update the reduction_status layer with all images of the stage set to status

            :param object reduction_metadata: the metadata object
            :param list new_images: list of string with the new images names
            :param int status: status of stage0 reduction for a frame. 0 : not done
                                                                      1 : done
        '''


        if self.reduction_status:
            layer = self.reduction_status
            length_table = len(layer[1])

            if length_table !=0:

                for key in layer[1].keys()[1:]:

                    self.update_column_to_layer('reduction_status', key,length_table*['0'])

    def get_gain(self):
        """Convenience method to return the camera gain, if the
        reduction_parameters layer has been loaded.  Otherwise, None is given.
        """

        try:
            gain = float(self.reduction_parameters[1]['GAIN'])
        except:
            gain = None
        return gain

    def get_readnoise(self):
        """Convenience method to return the camera read noise, if the
        reduction_parameters layer has been loaded.  Otherwise, None is given.
        """

        try:
            ron = float(self.reduction_parameters[1]['RON'])
        except:
            ron = None
        return ron

    def extract_exptime(self,image_name):
        """Convenience method to look up the exposure time for the indicated
        image from the headers_summary in the reduction metadata"""

        try:
            idx = list(self.headers_summary[1]['IMAGES']).index(image_name)

            exp_time = float(self.headers_summary[1]['EXPKEY'][idx])

        except TypeError:

            raise AttributeError('Cannot extract image exposure time as reduction headers summary not loaded into metadata')

        return exp_time

    def calc_psf_radii(self):

        idx = np.where(self.images_stats[1]['IM_NAME'].data == self.data_architecture[1]['REF_IMAGE'][0])

        fwhm_ref = self.images_stats[1]['FWHM'].data[idx[0][0]]

        psf_factors = self.psf_dimensions[1]['psf_factor'].data

        #psf_radii = psf_factors * fwhm_ref * 0.6731
        psf_radii = psf_factors * fwhm_ref
        self.psf_dimensions[1]['psf_radius'] = psf_radii

    def cone_search_on_position(self,params):
        """Function to search the star_catalog for stars within (radius) of the
        (ra_centre, dec_centre) given.

        :param float ra_centre: Box central RA in decimal degrees
        :param float dec_centre: Box central Dec in decimal degrees
        :param float radius:     Search radius in decimal degrees
        """

        starlist = SkyCoord(self.star_catalog[1]['ra'], self.star_catalog[1]['dec'],
                            frame='icrs', unit=(u.deg,u.deg))

        target = SkyCoord(params['ra_centre'], params['dec_centre'], frame='icrs', unit=(u.deg,u.deg))

        separations = target.separation(starlist)

        idx = np.where(separations.value <= params['radius'])

        results = Table( [Column(name='star_id', data=self.star_catalog[1]['index'][idx]),
                          Column(name='ra', data=self.star_catalog[1]['ra'][idx]),
                          Column(name='dec', data=self.star_catalog[1]['dec'][idx]),
                          Column(name='separation', data=separations[idx]) ])

        debug = False
        if debug and len(idx[0]) == 0:
            print('Nearest closest star: ')
            idx = np.where(separations.value <= separations.value.min())
            print(self.star_catalog[1]['index'][idx], self.star_catalog[1]['ra'][idx], self.star_catalog[1]['dec'][idx], separations[idx])

        return results

    def fetch_reduction_filter(self):
        """Function to identify the filter used for the reduction"""

        ref_path = self.data_architecture[1]['REF_PATH'][0]
        ref_filename = self.data_architecture[1]['REF_IMAGE'][0]

        ref_image_path = path.join(ref_path, ref_filename)

        image_header = image_handling.get_science_header(ref_image_path)

        return image_header['FILTER']

###
def set_pars(self, par_dict):
    for key, value in par_dict.items():
        setattr(self, key, value)


def set_reduction_paths(self, red_dir):
    """Method to establish the reduction directory path.  The directory
    basename will also be taken to be the reduction code
    e.g. ROME-FIELD-01_lsc_doma-1m0-05-fl15_ip
    and this will be used to set the path to the metadata file,
    e.g. ROME-FIELD-01_lsc_doma-1m0-05-fl15_ip_meta.fits
    """

    self.red_dir = red_dir
    self.red_code = path.basename(self.red_dir)
    self.metadata_file = path.join(self.red_dir, self.red_code + '_meta.fits')

def set_image_red_status(image_red_status, status, image_list=None):

    if image_list == None:
        image_list = image_red_status.keys()

    # Long-hand list handling implemented when array selection failed
    for image in image_list:
        stat = image_red_status[image]
        if stat != '-1':
            image_red_status[image] = status
        else:
            image_red_status[image] = '-1'

    return image_red_status

def write(self):
    """Method to output the reduction metadata in the pyDANDIA
    pipeline-standard multi-extension FITS binary table format.
    """

    hdulist = fits.HDUList()

    level0 = self.get_level0()
    hdulist.append(level0)

    level1 = self.get_level1()
    hdulist.append(level1)

    level2 = self.get_level2()
    hdulist.append(level2)

    level3 = self.get_level3()
    hdulist.append(level3)

    level4 = self.get_level4()
    hdulist.append(level4)

    hdulist.writeto(self.metadata_file, clobber=True)
    print('Output metadata to ' + self.metadata_file)


def build_hdu(self, data):
    """Method to construct a Primary Header Data Unit from a list of
    entries of the format:
    list [ self.attribute, keyword, format, comment_string]
    """

    hdu = fits.PrimaryHDU()
    for attr, key, keytype, comment in data:
        value = getattr(self, attr)
        if keytype == 'string':
            value = str(value)
        elif keytype == 'int':
            value = int(value)
        elif keytype == 'float':
            value = float(value)
        hdu.header[key] = (value, comment)

    return hdu


def get_level0(self):
    """Method that defines the FITS header keywords and comments for
    Level 0 of the pyDANDIA metadata file:
    Dataset description parameters
    """

    data = [['field', 'FIELD', 'string', 'Name of target field'],
            ['site', 'SITE', '5A', 'Site code'],
            ['enclosure', 'DOME', '10A', 'Dome code'],
            ['telescope', 'TEL', '20A', 'Telescope'],
            ['instrument', 'CAMERA', '20A', 'Instrument'],
            ['filter', 'FILTER', '20A', 'Filter'],
            ['binx', 'BINX', 'I5', 'Instrument binning factor in x-axis [pix]'],
            ['biny', 'BINY', 'I5', 'Instrument binning factor in y-axis [pix]'],
            ['pixel_scale', 'PIXSCALE', 'E', 'Pixel scale of instrument [arcsec/pix]'],
            ]

    hdu = self.build_hdu(data)

    return hdu


def get_level1(self):
    """Method that defines the FITS header keywords and comments for
    Level 1 of the pyDANDIA metadata file:
    Reduction configuration parameters
    """

    data = [['year', 'YEAR', 'int', 'Year of observations'],
            ['back_var', 'BACKVAR', 'string', 'Switch for a spatially variable differential background'],
            ['coeff2', 'COEFF2', 'float', ''],
            ['coeff3', 'COEFF3', 'float', ''],
            ['datekey', 'DATE-KEY', 'string', 'Name of date keyword in image headers'],
            ['deckey', 'DEC-KEY', 'string', 'Name of Declination keyword in image headers'],
            ['det_thresh', 'DETTHRS', 'float', 'Detection threshold [image sky sigma]'],
            ['diffpro', 'DIFFPRO', 'int', 'Switch for the method of difference image creation'],
            ['expfrac', 'EXPFRAC', 'float', 'Fraction of the exposure time to be added to the UTC'],
            ['expkey', 'EXP-KEY', 'string', 'Name of exposure time keyword in image header'],
            ['filtkey', 'FILT-KEY', 'string', 'Name of filter keyword in image header'],
            ['growsatx', 'GROWSATX', 'float', 'Half saturated pixel box size in the x direction [pix]'],
            ['growsaty', 'GROWSATY', 'float', 'Half saturated pixel box size in the y direction [pix]'],
            ['imagedx', 'IMAGE-DX', 'float', 'Width of image subframe [pix]'],
            ['imagedy', 'IMAGE-DY', 'float', 'Height of image subframe [pix]'],
            ['imagex1', 'IMAGEX1', 'int', 'Subframe starting pixel in x-axis [pix]'],
            ['imagex2', 'IMAGEX2', 'int', 'Subframe end pixel in x-axis [pix]'],
            ['imagexmax', 'IMGXMAX', 'int', 'Last pixel of image area in x-axis [pix]'],
            ['imagexmin', 'IMGXMIN', 'int', 'First pixel of image area in x-axis [pix]'],
            ['imagey1', 'IMAGEY1', 'int', 'Subframe starting pixel in y-axis [pix]'],
            ['imagey2', 'IMAGEY2', 'int', 'Subframe end pixel in y-axis [pix]'],
            ['imageymax', 'IMGYMAX', 'int', 'Last pixel of image area in y-axis [pix]'],
            ['imageymin', 'IMGYMIN', 'int', 'First pixel of image area in y-axis [pix]'],
            ['ker_rad', 'KERRAD', 'float', 'Radius of the kernel pixel array [FWHM]'],
            ['max_nim', 'MAX-NIM', 'int', 'Maximum number of images to combine for the reference image'],
            ['max_sky', 'MAX-SKY', 'float', 'Maximum allowed sky background [counts] for reference image'],
            ['min_ell', 'MIN-ELL', 'float', 'Minimum allowed ellipticity for reference image'],
            ['obskey', 'OBSTKEY', 'string', 'Name of data type keywork in image header'],
            ['obskeyb', 'OBSTBIAS', 'string', 'Obstype entry if image is a bias'],
            ['obskeyd', 'OBSTDARK', 'string', 'Obstype entry if image is a dark'],
            ['obskeyf', 'OBSTFLAT', 'string', 'Obstype entry if image is a flat'],
            ['obskeys', 'OBSTSCI', 'string', 'Obstype entry if image is a science image'],
            ['oscanx1', 'OSCANX1', 'int', 'Starting pixel of overscan region in x [pix]'],
            ['oscanx2', 'OSCANX2', 'int', 'End pixel of overscan region in x [pix]'],
            ['oscany1', 'OSCANY1', 'int', 'Starting pixel of overscan region in y [pix]'],
            ['oscany2', 'OSCANY2', 'int', 'End pixel of overscan region in y[pix]'],
            ['psf_comp_dist', 'PSFDIST', 'float', 'Minimum separation of PSF neighbour stars [PSF FWHM]'],
            ['psf_comp_flux', 'PSFCFLUX', 'float', 'Maximum flux ratio of PSF neighbour stars'],
            ['psf_corr_thresh', 'PSFCORRTHRESH', 'float', 'Minimum correlation coefficient for a PSF star'],
            ['psf_range_thresh', 'PSFRANGETHRESH', 'float', 'Brightest/faintest stars to exclude from PSF star selection [%]'],
            ['psf_size', 'PSFSIZE', 'float', 'Size of the model PSF stamp [PSF FWHM]'],
            ['ker_rad', 'KER_RAD', 'float', 'Kernel size [pix]'],
            ['rakey', 'RA-KEY', 'string', 'Name of RA keyword in image header'],
            ['subframes_x', 'SUBREGX', 'int', 'Number of image subregions in x-axis'],
            ['subframes_y', 'SUBREGY', 'int', 'Number of image subregions in y-axis'],
            ]

    hdu = self.build_hdu(data)

    return hdu


def get_level2(self):
    """Method that defines the FITS header keywords and comments for
    Level 2 of the pyDANDIA metadata file
    Data inventory
    """

    level2 = [[0, 'IMAGE', '100A', ''],
              [1, 'FIELD', '100A', ''],
              [2, 'DATE', '10A', 'UTC'],
              [3, 'TIME', '12A', 'UTC'],
              [4, 'PROCSTAT', '1A', ''],
              ]

    data = np.array(self.inventory)
    table = []
    for col, key, fstr, unit in level2:
        table.append(fits.Column(name=key, format=fstr,
                                 array=data[:, col],
                                 unit=unit))

    tbhdu = fits.BinTableHDU.from_columns(table)

    return tbhdu


def get_level3(self):
    """Method that defines the FITS header keywords and comments for
    Level 2 of the pyDANDIA metadata file
    Image data parameters (~old trendlog.imred)
    """

    level3 = [['image', 'IMAGE', '100A', ''],
              [0, 'HJD', 'E', ''],
              [1, 'EXPTIME', 'E', 's'],
              [2, 'SKYBKGD', 'E', 'counts'],
              [3, 'SKYSIG', 'E', 'counts'],
              [4, 'FWHM', 'E', 'pix'],
              [5, 'NSTARS', 'I', ''],
              [None, 'AIRMASS', 'E', ''],
              [None, 'MOONSEP', 'E', 'degrees'],
              [None, 'MOONFRAC', 'E', '%'],
              ]
    image_list = list(self.imred.keys())
    image_list.sort
    data = []
    for image in image_list:
        data.append(self.imred[image])
    data = np.array(data)
    table = []
    for col, key, fstr, unit in level3:
        if col == 'image':
            table.append(fits.Column(name=key, format=fstr,
                                     array=np.array(image_list),
                                     unit=unit))
        elif col != None and col > 0:
            table.append(fits.Column(name=key, format=fstr,
                                     array=data[:, col],
                                     unit=unit))
        else:
            table.append(fits.Column(name=key, format=fstr,
                                     array=np.zeros(len(data[:, 0])),
                                     unit=unit))
    tbhdu = fits.BinTableHDU.from_columns(table)

    return tbhdu


def get_level4(self):
    """Method that defines the FITS header keywords and comments for
    Level 2 of the pyDANDIA metadata file
    Geometric alignment parameters (~trendlog.gimred)
    """

    level1 = [['image', 'IMAGE', '100A', ''],
              [0, 'A0', 'E', ''],
              [1, 'A1', 'E', 's'],
              [2, 'A2', 'E', 'counts'],
              [3, 'A3', 'E', 'counts'],
              [4, 'A4', 'E', 'pix'],
              [5, 'A5', 'E', ''],
              [6, 'A6', 'E', ''],
              [7, 'NSMATCH', 'I', 'degrees'],
              [8, 'RMSX', 'E', '%'],
              [9, 'RMSY', 'E', '%'],
              ]

    image_list = list(self.gimred.keys())
    image_list.sort
    data = []
    for image in image_list:
        data.append(self.gimred[image])
    data = np.array(data)
    table = []
    for col, key, fstr, unit in level1:
        if col == 'image':
            table.append(fits.Column(name=key, format=fstr,
                                     array=np.array(image_list),
                                     unit=unit))
        elif col != None and col > 0:
            table.append(fits.Column(name=key, format=fstr,
                                     array=data[:, col],
                                     unit=unit))
        else:
            table.append(fits.Column(name=key, format=fstr,
                                     array=np.zeros(len(data[:, 0])),
                                     unit=unit))
    tbhdu = fits.BinTableHDU.from_columns(table)

    return tbhdu
