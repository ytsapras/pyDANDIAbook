# -*- coding: utf-8 -*-
"""
Created on Wed May  9 16:33:56 2018

@author: rstreet
"""
import os
import sys
from pyDANDIA import pipeline_setup
from pyDANDIA import logs
from pyDANDIA import metadata
from pyDANDIA import catalog_utils
from pyDANDIA import photometry
from pyDANDIA import vizier_tools
from pyDANDIA import gaia_phot_transforms

from astropy.coordinates import SkyCoord
from astropy.coordinates import matching
import astropy.units as u
from astropy.table import Table

import numpy as np
from scipy import optimize
from scipy.odr import *
import matplotlib as mpl
mpl.use('Agg')
import matplotlib.pyplot as plt
import json

VERSION = 'calibrate_photometry_0.5.1'

def calibrate_photometry_catalog(setup, **kwargs):
    """Function to calculate the photometric transform between the instrumental
    magnitudes produced by the pyDANDIA pipeline and catalog data."""

    log = logs.start_stage_log( setup.red_dir, 'phot_calib', version=VERSION )

    params = assign_parameters(setup,kwargs,log)

    (reduction_metadata, params) = fetch_metadata(setup,params,log)

    reduction_metadata = calibrate_photometry(setup, reduction_metadata, log, **kwargs)

    logs.close_log(log)

    status = 'OK'
    report = 'Completed successfully'

    return status, report

def calibrate_photometry(setup, reduction_metadata, log, **kwargs):
    """Function to perform a photometric calibration where the cross-matching
    with the VPHAS catalog has already been performed"""

    params = assign_parameters(setup,kwargs,log)

    (reduction_metadata, params, star_catalog) = extract_params_from_metadata(reduction_metadata, params, log)

    if params['set_phot_calib'] == False:
        star_catalog = select_calibration_stars(star_catalog,params,log)

        match_index = extract_matched_stars_index(star_catalog,params,log)

        if len(match_index) > 0:
            (fit,covar_fit) = calc_phot_calib(params,star_catalog,match_index,log)

            star_catalog = apply_phot_calib(star_catalog,fit,covar_fit,log)

            output_to_metadata(setup, params, fit, covar_fit, star_catalog, reduction_metadata, log)
        else:

            fit = [0,1]
            covar_fit = np.array([[0.0,0.0],[0.0,0.0]])
            sigma_fit = 0.0
            output_to_metadata(setup, params, fit, covar_fit, star_catalog, reduction_metadata, log)

    else:
        fit = [params['a0'], params['a1']]
        covar_fit = np.array([ [params['c0'],params['c1']],[params['c2'],params['c3']] ])

        log.info('Using provided photometric transformation parameters: a0='+\
                        str(params['a0'])+' a1='+str(params['a1'])+' and covarience matrix='+repr(covar_fit))

        star_catalog = apply_phot_calib(star_catalog,fit,covar_fit,log)

        output_to_metadata(setup, params, fit, covar_fit, star_catalog, reduction_metadata, log)

    return reduction_metadata

def get_args():
    """Function to gather the necessary commandline arguments"""

    params = { 'red_dir': '',
               'metadata': '',
               'log_dir': '',
               'pipeline_config_dir': '',
               'software_dir': '',
               'verbosity': '',
            }

    if len(sys.argv) > 1:
        params['red_dir'] = sys.argv[1]
        params['metadata'] = sys.argv[2]
        params['log_dir'] = sys.argv[3]

        if len(sys.argv) > 4:

            for a in sys.argv[4:]:
                if a[0:1] != '-':
                    (key,value) = a.split('=')
                    params[key] = value

    else:
        params['red_dir'] = input('Please enter the path to the reduction directory: ')
        params['metadata'] = input('Please enter the name of the metadata file: ')
        params['log_dir'] = input('Please enter the path to the log directory: ')
        params['det_mags_max'] = input('Please enter the faintest instrumental magnitude bin to use in calibration (or none to accept the defaults): ')
        params['det_mags_min'] = input('Please enter the brightest instrumental magnitude bin to use in calibration (or none to accept the defaults): ')
        params['cat_mags_max'] = input('Please enter the faintest catalog magnitude (or none to accept the defaults): ')
        params['cat_merr_max'] = input('Please enter the maximum allowed photometric uncertainty for a catalog measurement (or none to accept the defaults): ')

    for key in ['det_mags_max', 'det_mags_min', 'cat_merr_max', \
                'cat_mags_max', 'cat_mags_min']:
        if key in params.keys() and 'none' not in str(params[key]).lower():
            params[key] = float(params[key])
        else:
            params[key] = None

    params['set_phot_calib'] = False
    params['a0'] = None
    params['a1'] = None
    params['phot_calib_file'] = None
    params['use_gaia_phot'] = False
    for a in sys.argv:
        if '-use-gaia-phot' in a or '-use_gaia_phot' in a:
            params['use_gaia_phot'] = True
        if '-set-phot-calib' in a or '-set_phot_calib' in a:
            params['set_phot_calib'] = True
        if '-a0' in a:
            params['a0'] = float(str(a).split('=')[-1])
        if '-a1' in a:
            params['a1'] = float(str(a).split('=')[-1])
        if '-phot_calib_file' in a or '-phot-calib-file' in a:
            params['phot_calib_file'] = str(a).split('=')[-1]

    if params['set_phot_calib'] and params['phot_calib_file'] == None:
        raise ValueError('Set photometric calibration flag set to True but no photometric calibration file provided')

    if params['phot_calib_file'] != None:
        phot_calib = parse_phot_calibration_file(params['phot_calib_file'])
        for key, value in phot_calib.items():
            params[key] = value

    return params

def parse_phot_calibration_file(file_path):
    """Function to read in the parameters of the photometric calibration from
    a file

    File format should be:
    {
       "filter": "<filter ID>",
       "a0": <float>,
       "a1": <float>,
       "c0": <float>,
       "c1": <float>,
       "c2": <float>,
       "c3": <float>
    }
    """

    if not os.path.isfile(file_path):
        raise IOError('Cannot find photometric calibration file '+file_path)

    config_file = open(file_path,'r')
    config_dict = json.load(config_file)
    config_file.close()

    str_keys = ['filter']
    phot_calib = {}
    for key, value in config_dict.items():
        if key in str_keys:
            phot_calib[key] = value
        else:
            phot_calib[key] = float(value)

    return phot_calib

def assign_parameters(setup,cl_params,log):
    """Function to build a dictionary of the parameters required for the
    photometric calibration.  This construction enables the code to be run
    independently of the pipeline if necessary"""

    params = { 'red_dir': setup.red_dir,
               'metadata': os.path.join(setup.red_dir,'pyDANDIA_metadata.fits'),
               'log_dir': setup.log_dir }

    for key, value in cl_params.items():
        params[key] = value

    log.info('Configured parameters:')
    for key, value in cl_params.items():
        log.info(key+': '+str(value))

    return params

def fetch_metadata(setup,params,log):
    """Function to extract the information necessary for the photometric
    calibration from a metadata file, adding information to the params
    dictionary"""

    reduction_metadata = metadata.MetaData()
    reduction_metadata.load_a_layer_from_file( setup.red_dir,
                                              params['metadata'],
                                              'data_architecture' )
    reduction_metadata.load_a_layer_from_file( setup.red_dir,
                                               params['metadata'],
                                              'reduction_parameters' )
    reduction_metadata.load_a_layer_from_file( setup.red_dir,
                                              params['metadata'],
                                              'headers_summary' )
    reduction_metadata.load_a_layer_from_file( setup.red_dir,
                                              params['metadata'],
                                              'star_catalog' )

    try:
        reduction_metadata.load_a_layer_from_file( setup.red_dir,
                                              params['metadata'],
                                              'phot_calib' )
    except KeyError:
        pass

    return reduction_metadata, params

def extract_params_from_metadata(reduction_metadata, params, log):

    params['fov'] = reduction_metadata.reduction_parameters[1]['FOV'][0]
    params['refimage'] = reduction_metadata.data_architecture[1]['REF_IMAGE'][0]
    iref = reduction_metadata.headers_summary[1]['IMAGES'].tolist().index(params['refimage'])
    params['ra'] = reduction_metadata.headers_summary[1]['RAKEY'][iref]
    params['dec'] = reduction_metadata.headers_summary[1]['DECKEY'][iref]
    params['filter'] = reduction_metadata.headers_summary[1]['FILTKEY'][iref]
    if params['use_gaia_phot'] == True:
        params['cat_mag_col'] = 'gaia_'+params['filter'].replace('p','')+'mag'
        params['cat_err_col'] = 'gaia_'+params['filter'].replace('p','')+'mag_err'
    else:
        params['cat_mag_col'] = params['filter'].replace('p','') + 'mag'
        params['cat_err_col'] = 'e_'+params['filter'].replace('p','') + 'mag'

    params['target'] = SkyCoord([params['ra']], [params['dec']],
                        unit=(u.hourangle, u.deg))

    log.info('Gathered information from metadata file '+params['metadata']+':')
    log.info('Image field of view: '+str(params['fov'])+'sq. deg')
    log.info('Reference image: '+params['refimage']+\
                ', index '+str(iref)+' in dataset')
    log.info('Filter used for dataset: '+params['filter'])
    log.info('Pointing center coordinates: '+params['ra']+' '+params['dec'])

    star_catalog = Table()
    star_catalog['index'] = reduction_metadata.star_catalog[1]['index']
    star_catalog['RA'] = reduction_metadata.star_catalog[1]['ra']
    star_catalog['DEC'] = reduction_metadata.star_catalog[1]['dec']
    star_catalog['mag'] = reduction_metadata.star_catalog[1]['ref_mag']
    star_catalog['mag_err'] = reduction_metadata.star_catalog[1]['ref_mag_error']
    star_catalog['gaia_ra'] = reduction_metadata.star_catalog[1]['ra']
    star_catalog['gaia_dec'] = reduction_metadata.star_catalog[1]['dec']
    star_catalog['vphas_source_id'] = reduction_metadata.star_catalog[1]['vphas_source_id']
    star_catalog['vphas_ra'] = reduction_metadata.star_catalog[1]['vphas_ra']
    star_catalog['vphas_dec'] = reduction_metadata.star_catalog[1]['vphas_dec']
    star_catalog['gmag'] = reduction_metadata.star_catalog[1]['gmag']
    star_catalog['e_gmag'] = reduction_metadata.star_catalog[1]['gmag_error']
    star_catalog['rmag'] = reduction_metadata.star_catalog[1]['rmag']
    star_catalog['e_rmag'] = reduction_metadata.star_catalog[1]['rmag_error']
    star_catalog['imag'] = reduction_metadata.star_catalog[1]['imag']
    star_catalog['e_imag'] = reduction_metadata.star_catalog[1]['imag_error']
    #star_catalog['clean'] = reduction_metadata.star_catalog[1]['clean']
    star_catalog['clean'] = np.zeros(len(reduction_metadata.star_catalog[1]['cal_ref_mag']))
    star_catalog['cal_ref_mag'] = np.zeros(len(reduction_metadata.star_catalog[1]['cal_ref_mag']))
    star_catalog['cal_ref_mag_err'] = np.zeros(len(reduction_metadata.star_catalog[1]['cal_ref_mag_error']))
    star_catalog['cal_ref_flux'] = np.zeros(len(reduction_metadata.star_catalog[1]['cal_ref_flux']))
    star_catalog['cal_ref_flux_err'] = np.zeros(len(reduction_metadata.star_catalog[1]['cal_ref_flux_error']))

    (Gmag, Gmerr) = gaia_phot_transforms.gaia_flux_to_mag(reduction_metadata.star_catalog[1]['phot_g_mean_flux'],
                                                          reduction_metadata.star_catalog[1]['phot_g_mean_flux_error'],
                                                          passband="G")
    (BPmag, BPmerr) = gaia_phot_transforms.gaia_flux_to_mag(reduction_metadata.star_catalog[1]['phot_bp_mean_flux'],
                                                        reduction_metadata.star_catalog[1]['phot_bp_mean_flux_error'],
                                                        passband="G_BP")
    (RPmag, RPmerr) = gaia_phot_transforms.gaia_flux_to_mag(reduction_metadata.star_catalog[1]['phot_rp_mean_flux'],
                                                        reduction_metadata.star_catalog[1]['phot_rp_mean_flux_error'],
                                                        passband="G_RP")

    star_catalog['gaia_source_id'] = reduction_metadata.star_catalog[1]['gaia_source_id']
    star_catalog['gaia_Gmag'] = Gmag
    star_catalog['gaia_Gmag_err'] = Gmerr
    star_catalog['gaia_BPmag'] = BPmag
    star_catalog['gaia_BPmag_err'] = BPmerr
    star_catalog['gaia_RPmag'] = RPmag
    star_catalog['gaia_RPmag_err'] = RPmerr

    (BP_RP, BPRPerr) = gaia_phot_transforms.calc_gaia_colours(star_catalog['gaia_BPmag'],star_catalog['gaia_BPmag_err'],
                                               star_catalog['gaia_RPmag'],star_catalog['gaia_RPmag_err'])
    star_catalog['gaia_BP_RP'] = BP_RP
    star_catalog['gaia_BPRP_err'] = BPRPerr

    phot = gaia_phot_transforms.transform_gaia_phot_to_SDSS(star_catalog['gaia_Gmag'], star_catalog['gaia_Gmag_err'],
                                        BP_RP, BPRPerr)
    star_catalog['gaia_gmag'] = phot['g']
    star_catalog['gaia_gmag_err'] = phot['g_err']
    star_catalog['gaia_rmag'] = phot['r']
    star_catalog['gaia_rmag_err'] = phot['r_err']
    star_catalog['gaia_imag'] = phot['i']
    star_catalog['gaia_imag_err'] = phot['i_err']

    phot = gaia_phot_transforms.transform_gaia_phot_to_JohnsonCousins(star_catalog['gaia_Gmag'], star_catalog['gaia_Gmag_err'],
                                        BP_RP, BPRPerr)
    star_catalog['gaia_Vmag'] = phot['V']
    star_catalog['gaia_Vmag_err'] = phot['V_err']
    star_catalog['gaia_Rmag'] = phot['R']
    star_catalog['gaia_Rmag_err'] = phot['R_err']
    star_catalog['gaia_Imag'] = phot['I']
    star_catalog['gaia_Imag_err'] = phot['I_err']

    log.info('Extracted star catalog')

    return reduction_metadata, params, star_catalog

def fetch_catalog_sources_within_image(params,log):
    """Function to extract the objects from the VPHAS+ catalogue within the
    field of view of the reference image, based on the metadata information.
    NOW DEPRECIATED"""

    params['radius'] = (np.sqrt(params['fov'])/2.0)*60.0

    log.info('VPHAS+ catalog search parameters: ')
    log.info('RA = '+str(params['ra'])+', Dec = '+str(params['dec']))
    log.info('Radius: '+str(params['radius'])+' arcmin')

    vphas_cat = vizier_tools.search_vizier_for_sources(params['ra'],
                                                       params['dec'],
                                                        params['radius'],
                                                        'VPHAS+',
                                                        row_limit=-1)

    log.info('VPHAS+ search returned '+str(len(vphas_cat))+' entries')

    return vphas_cat

def select_calibration_stars(star_catalog,params,log):
    """Function to identify and flag  stars suitable for the photometric
    calibration.  Based on code by Y. Tsapras."""

    if params['use_gaia_phot'] == True:
        cat_name = 'Gaia'
        cat_source_id_col = 'gaia_source_id'
        passbands = { 'G': {'mag_col': 'gaia_Gmag', 'merr_col': 'gaia_Gmag_err'},
                     'BP': {'mag_col': 'gaia_BPmag', 'merr_col': 'gaia_BPmag_err'},
                     'RP': {'mag_col': 'gaia_RPmag', 'merr_col': 'gaia_RPmag_err'} }
    else:
        cat_name = 'VPHAS+'
        cat_source_id_col = 'vphas_source_id'
        passbands = { 'g': {'mag_col': 'gmag', 'merr_col': 'e_gmag'},
                      'r': {'mag_col': 'rmag', 'merr_col': 'e_rmag'},
                      'i': {'mag_col': 'imag', 'merr_col': 'e_imag'} }

    # Catalog selection limits
    jdx = np.where(star_catalog[cat_source_id_col] != 'None')
    log.info(cat_name+' data available for '+str(len(jdx[0]))+' stars in total')

    limit_mag = 22.0
    #if params['filter'] == 'gp': limit_mag = 22.0
    #if params['filter'] == 'rp': limit_mag = 18.0

    if 'cat_mags_max' in params.keys() and params['cat_mags_max'] > limit_mag:
        limit_mag = params['cat_mags_max']

    log.info('Using limiting mag '+str(limit_mag)+\
                    ' for catalog selection for filter '+params['filter'])

    # First selecting stars with suitable VPHAS+ catalogue information
    idx = []
    for f,col_names in passbands.items():

        med = np.median(star_catalog[col_names['merr_col']][np.where(star_catalog[col_names['merr_col']]>0)])

        max_err = 2.0 * med
        if np.isnan(max_err):
            max_err = 0.02

        if 'cat_merr_max' in params.keys():
            max_err = params['cat_merr_max']

        log.info('Median photometric uncertainty ('+f+'-band) of catalog stars: '+str(med))
        log.info('Excluding catalog stars ('+f+'-band) with uncertainty > '+str(max_err))

        idx1 = np.where(star_catalog[col_names['merr_col']] <= max_err)
        idx2 = np.where(star_catalog[col_names['merr_col']] > 0)
        idx3 = np.where(star_catalog[col_names['mag_col']] < limit_mag)

        if len(idx1[0]) == 0:
            log.info('No catalog stars with magnitude errors <='+str(max_err))
            raise ValueError('No catalog stars with magnitude errors <='+str(max_err))

        if len(idx2[0]) == 0:
            log.info('No catalog stars with magnitudes > 0.0')
            raise ValueError('No catalog stars with magnitudes > 0.0')

        if len(idx3[0]) == 0:
            log.info('No catalog stars brighter than '+str(limit_mag))
            raise ValueError('No catalog stars brighter than '+str(limit_mag))

        jdx = (set(idx1[0]).intersection(set(idx2[0]))).intersection(set(idx3[0]))

        if len(idx) == 0:
            idx = list(idx) + list(jdx)
        else:
            idx = list(set(idx).intersection(jdx))

    star_catalog['clean'][idx] = 1.0

    log.info('Selected '+str(len(idx))+\
            ' stars with '+cat_name+' data suitable for use in photometric calibration')

    # Now selecting stars with good quality photometry from the ROME data and
    # Gaia positional data:
    idx0 = np.where(star_catalog['clean'] == 1.0)[0].tolist()
    idx1 = np.where(star_catalog['mag'] > 10.0)[0].tolist()
    idx2 = np.where(star_catalog['mag_err'] > 0.0)[0].tolist()
    idx3 = np.where(star_catalog['gaia_ra'] != 0.0)[0].tolist()
    idx = set(idx0).intersection(set(idx1))
    idx = idx.intersection(set(idx2))
    idx = idx.intersection(set(idx3))

    log.info('Of these, identified '+str(len(list(idx)))+' detected stars with good photometry')
    log.info('Selection critieria cuts:')
    log.info('N stars with clean detected photometry: '+str(len(idx0)))
    log.info('N stars with mag>10.0: '+str(len(idx1)))
    log.info('N stars with mag_err>0.0: '+str(len(idx2)))
    log.info('N stars with Gaia match: '+str(len(idx3)))

    # Now selecting stars close to the nominal target coordinates.
    # These default to the centre of the field if not otherwise given.
    # THIS CODE DEATIVATED FOR NOW, SINCE NOT IN DEFAULT USE BUT MAYBE
    # USEFUL IN FUTURE
    select_on_position = False
    if select_on_position:

        tol = 3.0*u.arcmin

        log.info('Selecting stars with '+repr(tol)+' of designated position '+\
                repr(params['target']))

        stars = SkyCoord(star_catalog['RA'], star_catalog['DEC'], unit="deg")

        separations = params['target'].separation(stars)

        jdx = np.where(separations < tol)

        log.info('Found '+str(len(list(jdx[0])))+' detected stars around target location')

        kdx = list(idx.intersection(set(jdx[0])))

        if len(jdx[0]) < 100 or len(kdx) < 100:
            kdx = list(idx)

            log.info('WARNING: Could not selected on position; too few detected stars with good photometry around target location')

    else:

        kdx = list(idx)

    star_catalog['clean'] = np.zeros(len(star_catalog['clean']))
    star_catalog['clean'][kdx] = 1.0

    log.info('Selected '+str(len(kdx))+' stars with good detected and catalog photometry')

    return star_catalog

def match_stars_by_position(star_catalog,log):
    """Function to cross-match stars by position.
    DEPRECIATED
    Returns:
        :param dict match_index: { Index in vphas_cat: index in star_cat }
    """

    ddx = np.where(star_catalog['clean'] == 1.0)[0]

    det_stars = SkyCoord(star_catalog['RA'][ddx], star_catalog['DEC'][ddx], unit="deg")

    vdx = np.where(vphas_cat['clean'] == 1.0)[0]

    cat_stars = SkyCoord(vphas_cat['_RAJ2000'][vdx], vphas_cat['_DEJ2000'][vdx], unit="deg")

    tolerance = 2.0 * u.arcsec

    match_data = matching.search_around_sky(det_stars, cat_stars,
                                             seplimit=tolerance)

    idx = np.argsort(match_data[2].value)

    det_index = match_data[0][idx]
    cat_index = match_data[1][idx]

    match_index = np.array(list(zip(ddx[det_index],vdx[cat_index])))

    if len(match_index) > 0:
        log.info('Matched '+str(len(match_index)))
    else:
        raise ValueError('Could not match any catalog stars')

    return match_index

def extract_matched_stars_index(star_catalog,params,log):
    """Function to extracted a match_stars index dictionary of stars
    cross-matched by position.

    Returns:
        :param array match_index: [[Index in selected catalog, index in detected_stars]]
    """

    match_index = {}

    # By default, this selects all stars with VPHAS data.
    if params['use_gaia_phot']:
        ddx = np.where(star_catalog['gaia_source_id'] != 'None')[0]
    else:
        ddx = np.where(star_catalog['clean'] == 1.0)[0]

    if len(ddx) == 0:
        log.info('Insufficient matched stars to continue photometric calibration')
        match_index = np.zeros([0,2], dtype=int)
        return match_index

    else:
        log.info('Using '+str(len(ddx))+' in photometric calibration')

    match_index = np.zeros([len(ddx),2], dtype=int)

    match_index[:,0] = ddx.astype(int)
    match_index[:,1] = ddx.astype(int)

    if len(match_index) > 0:
        log.info('Matched '+str(len(match_index)))
    else:
        raise ValueError('Could not match any catalog stars')

    return match_index

def calc_phot_calib(params,star_catalog,match_index,log):
    """Function to plot the photometric calibration"""

    cmag = params['cat_mag_col']
    cerr = params['cat_err_col']

    fit = [0.0, 0.0]

    (fit,covar_fit) = model_phot_transform2(params,star_catalog,
                                   match_index,fit,log)

    if fit[0] > -9999.0:
        for i in range(0,1,1):

            (fit,covar_fit) = model_phot_transform2(params,star_catalog,
                                       match_index,fit,log, diagnostics=True)

            log.info('Fit result ['+str(i)+']: '+repr(fit))
            log.info('Fit covarience: '+repr(covar_fit))

            match_index = exclude_outliers(star_catalog,params,
                                            match_index,fit,log)

        log.info('Final fitted photometric calibration: '+repr(fit))

    return fit, covar_fit

def model_phot_transform(params,star_catalog,vphas_cat,match_index,fit,
                         log, diagnostics=True):
    """Function to make an initial guess at the fit parameters
    WARNING: Not upgraded for the integration of the VPHAS+ with the star_catalog
    """


    log.info('Fit initial parameters: '+repr(fit))

    cmag = params['cat_mag_col']
    cerr = params['cat_err_col']

    cat_mags = vphas_cat[cmag][match_index[:,1]]
    cat_merrs = vphas_cat[cerr][match_index[:,1]]
    det_mags = star_catalog['mag'][match_index[:,0]]

    config = set_calibration_limits(params,log)

    xibin = 0.5
    xbin1 = config['det_mags_max']
    xbin2 = xbin1 - xibin

    binned_data = []
    peak_bin = []
    xbins = []
    ybins = []

    while xbin2 > config['det_mags_min']:

        idx1 = np.where(det_mags <= xbin1)
        idx2 = np.where(det_mags > xbin2)
        idx = list(set(idx1[0].tolist()).intersection(set(idx2[0].tolist())))

#        print 'X: ',xbin1,xbin2, len(idx)

        if len(idx) > 0:

            ybin1 = cat_mags.max()
            yibin = 0.5
            ybin2 = ybin1 - yibin

            xbin_max = 0.0
            ybin_max = 0.0
            row_max = 0

            while ybin2 > cat_mags.min():

                jdx1 = np.where(cat_mags[idx] <= ybin1)
                jdx2 = np.where(cat_mags[idx] > ybin2)
                jdx3 = np.where(cat_merrs[idx] <= config['cat_merr_max'])
                jdx = set(jdx1[0].tolist()).intersection(set(jdx2[0].tolist()))
                jdx = list(set(jdx).intersection(set(jdx3[0].tolist())))

                if len(jdx) > 0:

                    kdx = (np.array(idx)[jdx]).tolist()

                    row = []
                    row.append( (xbin1 - (xibin/2.0)) )
                    row.append( (ybin1 - (yibin/2.0)) )
                    row.append(np.median(cat_mags[kdx]))
                    row.append(len(kdx))

                    binned_data.append(row)
#                    print ' -> Y: ',ybin1,ybin2,row

                    if len(kdx) > row_max:
                        xbin_max = (xbin1 - (xibin/2.0))
                        ybin_max = np.median(cat_mags[kdx])
                        row_max = len(kdx)

                ybin1 -= yibin
                ybin2 = ybin1 - yibin

            if row_max > 5:
                xbins.append(xbin_max)
                ybins.append(ybin_max)
                peak_bin.append(row_max)
#                print 'Local maximum: ',xbins[-1], ybins[-1], peak_bin[-1], row_max

        xbin1 -= xibin
        xbin2 = xbin1 - xibin

    xbins = np.array(xbins)
    ybins = np.array(ybins)

    (fit,covar_fit) = calc_transform(fit, xbins, ybins)

    if diagnostics:

        f = open(os.path.join(params['red_dir'],'binned_phot.dat'),'w')
        for i in range(0,len(xbins),1):
            f.write(str(xbins[i])+' '+str(ybins[i])+'\n')
        f.close()

        fig = plt.figure(2)

        plt.errorbar(star_catalog['mag'][match_index[:,0]],
                     vphas_cat[cmag][match_index[:,1]],
                     xerr=star_catalog['mag_err'][match_index[:,0]],
                     yerr=vphas_cat[cerr][match_index[:,1]],
                     color='m', fmt='none')

        plt.plot(xbins,ybins,'g+',markersize=4)

        xplot = np.linspace(xbins.min(),xbins.max(),50)
        yplot = phot_func(fit,xplot)

        plt.plot(xplot, yplot,'k-')

        plt.xlabel('Instrumental magnitude')

        plt.ylabel('VPHAS+ catalog magnitude')

        [xmin,xmax,ymin,ymax] = plt.axis()

        plt.axis([xmax,xmin,ymax,ymin])

        plt.savefig(os.path.join(params['red_dir'],
                    'phot_model_transform_'+params['filter']+'.png'))

        plt.close(2)

    log.info('Fitted parameters: '+repr(fit))

    return fit

def set_calibration_limits(params,log):
    """Function to use the parameters given or set defaults"""

    if params['use_gaia_phot']:
        defaults = {'gp': {'det_mags_max': 21.0,
                           'det_mags_min': 15.0,
                           'cat_merr_max': 0.2},
                    'rp': {'det_mags_max': 21.0,
                           'det_mags_min': 15.0,
                           'cat_merr_max': 0.07},
                    'ip': {'det_mags_max': 21.0,
                           'det_mags_min': 15.0,
                           'cat_merr_max': 0.11},
                    'V': {'det_mags_max': 21.0,
                           'det_mags_min': 15.0,
                           'cat_merr_max': 0.2},
                    'R': {'det_mags_max': 21.0,
                           'det_mags_min': 15.0,
                           'cat_merr_max': 0.07},
                    'I': {'det_mags_max': 21.0,
                           'det_mags_min': 15.0,
                           'cat_merr_max': 0.11},
                           }
    else:
        defaults = {'gp': {'det_mags_max': 21.0,
                           'det_mags_min': 15.0,
                           'cat_merr_max': 0.03},
                    'rp': {'det_mags_max': 21.0,
                           'det_mags_min': 15.0,
                           'cat_merr_max': 0.03},
                    'ip': {'det_mags_max': 21.0,
                           'det_mags_min': 15.0,
                           'cat_merr_max': 0.03},
                    'V': {'det_mags_max': 21.0,
                           'det_mags_min': 15.0,
                           'cat_merr_max': 0.2},
                    'R': {'det_mags_max': 21.0,
                           'det_mags_min': 15.0,
                           'cat_merr_max': 0.07},
                    'I': {'det_mags_max': 21.0,
                           'det_mags_min': 15.0,
                           'cat_merr_max': 0.11},
                    }

    def_params = defaults[params['filter']]

    set_params = {}

    log.info('Set calibration limits: ')
    for key in ['det_mags_max', 'det_mags_min', 'cat_merr_max']:

        if key in params.keys():

            if params[key] != None:
                set_params[key] = params[key]
            else:
                set_params[key] = def_params[key]

        else:

            set_params[key] = def_params[key]

        log.info(key+' = '+str(set_params[key]))

    return set_params

def model_phot_transform2(params,star_catalog,match_index,fit,
                         log, diagnostics=True):
    """Function to make an initial guess at the fit parameters"""


    log.info('Fit initial parameters: '+repr(fit))

    cmag = params['cat_mag_col']
    cerr = params['cat_err_col']

    if cmag not in star_catalog.colnames or cerr not in star_catalog.colnames:
        log.info('WARNING: No catalog photometry available to automatically calibrate instrumental data in '+params['filter'])
        fit = np.array([-9999.9999, -9999.9999])
        covar_fit = np.zeros((2,2))

        return fit, covar_fit

    else:
        fit = np.array([1,0])
        covar_fit = np.zeros((2,2))
        log.info('Using catalog photometry columns: '+cmag+', '+cerr)

        cat_mags = star_catalog[cmag][match_index[:,1]]
        cat_merrs = star_catalog[cerr][match_index[:,1]]
        det_mags = star_catalog['mag'][match_index[:,0]]
        det_mag_errs = star_catalog['mag_err'][match_index[:,0]]

        config = set_calibration_limits(params,log)

        k = np.where((cat_merrs <= config['cat_merr_max']) & (np.abs(cat_mags-15)<10))[0]
        cat_mags = cat_mags[k]
        cat_merrs = cat_merrs[k]
        det_mags = det_mags[k]
        det_mag_errs = det_mag_errs[k]

        xibin = 0.5
        xbin1 = config['det_mags_max']
        xbin2 = xbin1 - xibin

        binned_data = []
        peak_bin = []
        xbins = []
        ybins = []

        (hist_data,xedges,yedges) = np.histogram2d(det_mags,cat_mags,bins=24)
        #hist_data = hist_data.T
        #import pdb; pdb.set_trace()

        idx = np.where(hist_data < (hist_data.max()*0.05))
        hist_data[idx] = 0

        idx = np.where(hist_data > (hist_data.max()*0.05))
        xcenters = (xedges[:-1] + xedges[1:]) / 2
        ycenters = (yedges[:-1] + yedges[1:]) / 2

        k1 = np.where(xcenters[idx[0]] < config['det_mags_max'])[0]
        k2 = np.where(xcenters[idx[0]] >= config['det_mags_min'])[0]
        k = list(set(k1).intersection(set(k2)))

        xbins = xcenters[idx[0][k]]
        ybins = []
        for x in idx[0][k]:

            k = np.where(hist_data[x,:] == (hist_data[x,:].max()))
            ybins.append(ycenters[k][0])

        if len(xbins) <= 1 or len(ybins) <= 1:
            log.info('Insufficient datapoints selected by calibration magnitude limits')

            return fit, covar_fit

        (fit,covar_fit) = calc_transform(fit, xbins, ybins)

        if diagnostics:

            f = open(os.path.join(params['red_dir'],'binned_phot.dat'),'w')
            f.write('# Instrmental_mag   Catalog_mag\n')
            for i in range(0,len(xbins),1):
                f.write(str(xbins[i])+' '+str(ybins[i])+'\n')
            f.close()

            f = open(os.path.join(params['red_dir'],'unbinned_phot.dat'),'w')
            f.write('# Detected_mag Detected_magerr  Catalog_mag  Catalog_magerr\n')
            for j in range(0,len(cat_mags),1):
                f.write(str(det_mags[j])+' '+str(det_mag_errs[j])+' '+\
                        str(cat_mags[j])+' '+str(cat_merrs[j])+'\n')
            f.close()

            plot_file = os.path.join(params['red_dir'],
                        'phot_model_transform_'+params['filter']+'.png')
            if os.path.isfile(plot_file):
                os.remove(plot_file)

            fig = plt.figure(3)

            plt_errs = False
            if plt_errs:
                plt.errorbar(star_catalog['mag'][match_index[:,0]],
                         star_catalog[cmag][match_index[:,1]],
                         xerr=star_catalog['mag_err'][match_index[:,0]],
                         yerr=star_catalog[cerr][match_index[:,1]],
                         color='m', fmt='none')
            else:
                plt.plot(star_catalog['mag'][match_index[:,0]],
                         star_catalog[cmag][match_index[:,1]],'m.', markersize=1)

            plt.plot(xbins,ybins,'g+',markersize=4)

            xplot = np.linspace(xbins.min(),xbins.max(),50)
            yplot = phot_func(fit,xplot)

            plt.plot(xplot, yplot,'k-')

            plt.xlabel('Instrumental magnitude')

            cat_name = 'VPHAS+'
            if params['use_gaia_phot']: cat_name = '(Transformed to SDSS) Gaia'
            plt.ylabel(cat_name+' catalog magnitude')

            [xmin,xmax,ymin,ymax] = plt.axis()

            plt.axis([xmax,xmin,ymax,ymin])

            plt.grid()

            plt.savefig(plot_file)

            plt.close(3)

        log.info('Fitted parameters: '+repr(fit))

        return fit, covar_fit

def phot_weighted_mean(data,sigma):
    """Function to calculate the mean of a set of magnitude measurements,
    weighted by their photometric errors"""

    sig2 = sigma * sigma
    wmean = (data/sig2).sum() / (1.0/sig2).sum()
    sig_wmean = 1.0 / (1.0/sig2).sum()

    return wmean, sig_wmean

def phot_func(p,mags):
    """Photometric transform function"""
    # Expected function is of the form p[0]*mags + p[1]
    if len(p) == 2:
        return np.polyval(p,mags)
    else:
        raise IndexError('Photometric transform called with an unexpected number of terms')

def errfunc(p,x,y):
    """Function to calculate the residuals on the photometric transform"""

    return y - phot_func(p,x)

def calc_transform(pinit, x, y):
    """Function to calculate the photometric transformation between a set
    of catalogue magnitudes and the instrumental magnitudes for the same stars
    """

    #(pfit,iexec) = optimize.leastsq(errfunc,pinit,args=(x,y))
    #(pfit,covar_fit) = np.polyfit(x,y,1,cov=True)
    linear_model = Model(phot_func)
    dataset = Data(x, y)
    odr_obj = ODR(dataset, linear_model, beta0=pinit)
    results = odr_obj.run()

    pfit = np.array([results.beta[0], results.beta[1]])
    covar_fit = results.cov_beta*results.res_var

    return pfit, covar_fit

def calc_transform_uncertainty(pfit, x, y):
    """Function to calculate the uncertainty on the calibrated magnitudes,
    based on the scatter of datapoints around the fitted model
    See: http://123.physics.ucdavis.edu/week_0_files/taylor_181-199.pdf
    """

    y2 = phot_func(pfit,x)
    delta = (y - y2)**2
    sigma_y2 = np.sqrt(delta.sum()/float(len(delta)-2))

    return sigma_y2

def exclude_outliers(star_catalog,params,match_index,fit,log):

    cmag = params['cat_mag_col']

    pred_mags = phot_func(fit, (star_catalog[cmag][match_index[:,1]]) )

    residuals = star_catalog['mag'][match_index[:,0]] - pred_mags

    (median,MAD) = calc_MAD(residuals)

    log.info('Median, MAD of photometric residuals: '+str(median)+' '+str(MAD))

    jdx = np.where(residuals >= (median - 3.0*MAD))[0]
    kdx = np.where(residuals <= (median + 3.0*MAD))[0]
    dx = list(set(jdx).intersection(set(kdx)))

    log.info('Excluded '+str(len(match_index)-len(dx))+', '+\
            str(len(match_index))+' stars remaining')

    match_index = np.array(list(zip(match_index[dx,0],match_index[dx,1])))

    return match_index

def calc_MAD(x):
    """Function to calculate the Median Absolute Deviation from a single-column
    array of floats"""

    median = np.median(x)
    MAD = np.median(abs(x - np.median(x)))

    return median, MAD

def calc_calibrated_mags(fit_params, covar_fit, star_catalog, log):

    ''' In this function, we propagate uncertainties of the mag calibration. The formula is:

        cal_mag = a*mag+b [where a is fixed to 1.0]

        Therefore, the covariance matrix and Jacobian are:

        C = |sig_a**2 sig_ab 0|
            |sig_ab sig_b**2 0|
            |0       0 e_mag**2|

        J = [mag,1,a]

        and then

        e_cal_mag = J.T C J


        HOWEVER

        for computing reason, we implemented a modified version with identical result:

        C' = |sig_a**2 sig_ab 0|
             |sig_ab sig_b**2 0|
             |0       0 a**2|

        J' = [mag,1,e_mag]

        and

        e_cal_mag = J'.T C' J'

    '''

    log.info('-> Calculating calibrated mag uncertainties from covarience matrix')

    ccalib = np.eye(3)
    ccalib[:2,:2] = covar_fit
    ccalib[2,2] = fit_params[0]**2
    log.info(repr(ccalib))
    jac = np.c_[star_catalog['mag'], [1]*len(star_catalog), star_catalog['mag_err']]
    star_catalog['cal_ref_mag'] = phot_func(fit_params,star_catalog['mag'])
    #res = jac@np.dot(ccalib,jac.T)
    #res = np.dot(jac,np.dot(ccalib,jac.T))
    #star_catalog['cal_ref_mag_err'] = res.diagonal()**0.5
    errors = []
    for i in range(len(jac)):
        vect = []
        for j in range(len(ccalib)):
            vect.append(np.sum(ccalib[j]*jac[i]))
        errors.append(np.sum(vect*jac[i])**0.5)
    star_catalog['cal_ref_mag_err'] = errors
    idx = np.where(star_catalog['mag'] < 7.0)
    star_catalog['cal_ref_mag'][idx] = 0.0
    star_catalog['cal_ref_mag_err'][idx] = 0.0

    return star_catalog

def apply_phot_calib(star_catalog,fit_params,covar_fit,log):
    """Function to apply the computed photometric calibration to calculate
    calibrated magnitudes for all detected stars"""

    log.info('Applying the photometric calibration')

    mags = star_catalog['mag']

    if fit_params[0] > -9999.0 and fit_params[1] > -9999.0:
        star_catalog = calc_calibrated_mags(fit_params, covar_fit, star_catalog, log)

        (cal_flux, cal_flux_error) = photometry.convert_mag_to_flux(star_catalog['cal_ref_mag'],
                                                                    star_catalog['cal_ref_mag_err'])

        star_catalog['cal_ref_flux'] = cal_flux
        star_catalog['cal_ref_flux_err'] = cal_flux_error

        log.info('Calculated calibrated reference magnitudes for all detected stars')

    else:
        log.info('Photometric transformation invalid, no calibrated magnitudes produced')

    return star_catalog

def output_to_metadata(setup, params, phot_fit, covar_fit, star_catalog, reduction_metadata, log):
    """Function to output the star catalog to the reduction metadata.
    Creates a phot_catalog extension if none exists, or overwrites an
    existing one"""

    cmag = params['cat_mag_col']

    reduction_metadata.star_catalog[1]['index'] = star_catalog['index'][:]
    reduction_metadata.star_catalog[1]['cal_ref_mag'] = star_catalog['cal_ref_mag'][:]
    reduction_metadata.star_catalog[1]['cal_ref_mag_error'] = star_catalog['cal_ref_mag_err'][:]
    reduction_metadata.star_catalog[1]['cal_ref_flux'] = star_catalog['cal_ref_flux'][:]
    reduction_metadata.star_catalog[1]['cal_ref_flux_error'] = star_catalog['cal_ref_flux_err'][:]

    log.info('Updating star_catalog table')

    reduction_metadata.save_a_layer_to_file(setup.red_dir,
                                            params['metadata'],
                                            'star_catalog', log=log)

    reduction_metadata.create_phot_calibration_layer(phot_fit, covar_fit)

    reduction_metadata.save_a_layer_to_file(setup.red_dir,
                                            params['metadata'],
                                            'phot_calib', log=log)

def run_calibration():
    """Function to run this stage independently of the pipeline infrastructure"""

    kwargs = get_args()

    setup = pipeline_setup.pipeline_setup(kwargs)

    (status, report) = calibrate_photometry_catalog(setup, **kwargs)

if __name__ == '__main__':

    run_calibration()
