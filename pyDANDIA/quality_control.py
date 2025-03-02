# -*- coding: utf-8 -*-
"""
Created on Mon Aug 27 13:34:31 2018

@author: rstreet
"""
import os
from astropy.io import fits
from astropy import units as u
from astropy.coordinates import SkyCoord
import numpy as np
from pyDANDIA import metadata
from astropy.stats import mad_std,sigma_clipped_stats
from astropy.table import Table
from astropy.table import Column

def verify_stage0_output(setup,log):
    """Function to verify that stage 0 has produced the expected output.

    This function checks for the presences of a metadata file and a stage log
    """

    log.info('Verifying stage 0 data products:')

    status = 'OK'
    report = 'Completed successfully'

    metadata_file = os.path.join(setup.red_dir, 'pyDANDIA_metadata.fits')
    stage_log = os.path.join(setup.red_dir, 'stage0.log')

    if os.path.isfile(metadata_file) == False or os.path.isfile(stage_log) == False:

        status = 'ERROR'
        report = 'Stage 0 finished without producing its expected data products'

        log.info('Status: '+status)
        log.info('Report: '+report)

        return status, report

    m = fits.open(metadata_file)

    if len(m) < 6:

        status = 'ERROR'
        report = 'Stage 0 produced an incomplete metadata file'

        log.info('Status: '+status)
        log.info('Report: '+report)

        return status, report

    log.info('Status: '+status)
    log.info('Report: '+report)

    return status, report

def assess_image(reduction_metadata,image_params,image_header,log):
    """Function to assess the quality of an image, and flag any which should
    be considered suspect.  Flagged images, particularly those taken in
    conditions of poor seeing, can dramatically affect the reduction timescale.

    Inputs:
        :param Metadata reduction_metadata: Metadata for the reduction, including
                                            the reduction parameters table
        :param dict image_params: Measured parameters of the image including
                                  the FWHM, sky background and number of stars

    Outputs:
        :param int use_phot: Quality flag whether this image can be used for photometry
        :param int use_ref: Quality flag whether this image could be used for a reference
        :param int use_image: Quality flag whether this image should be reduced at all

    Flag convention: 1 = OK, 0 = bad image
    """

    use_phot = 1
    use_ref = 1
    use_image = 1
    report = ''

    sigma_max = reduction_metadata.reduction_parameters[1]['MAX_SIGMA_PIXELS'][0]
    sky_max = reduction_metadata.reduction_parameters[1]['MAX_SKY'][0]
    sky_ref_max = reduction_metadata.reduction_parameters[1]['MAX_SKY_REF'][0]

    if image_params['nstars'] == 0:
        use_phot = 0
        use_ref = 0
        use_image = 0
        report = append_errors(report, 'No stars detected in frame')

    if image_params['sigma_x'] > sigma_max or image_params['sigma_y'] > sigma_max:
        use_phot = 0
        use_ref = 0
        report = append_errors(report, 'FWHM exceeds threshold')

    if image_params['sigma_x'] < 0.0 or image_params['sigma_y'] < 0.0:
        use_phot = 0
        use_ref = 0
        use_image = 0
        report = append_errors(report, 'FWHM negative')

    if image_params['sky'] > sky_max:
        use_phot = 0
        report = append_errors(report, 'Sky background exceeds threshold for photometry')

    if image_params['sky'] > sky_ref_max:
        use_ref = 0
        report = append_errors(report, 'Sky background exceeds threshold for reference')

    if not verify_telescope_pointing(image_header):
        use_image = 0
        use_phot = 0
        use_ref = 0
        report = append_errors(report, 'Telescope pointing error exceeds threshold')

    if use_phot == 1 and use_ref == 1 and use_image == 1 and len(report) == 0:
        report = 'OK'

    log.info('Quality assessment:')
    log.info('Use for photometry = '+str(use_phot))
    log.info('Use for reference = '+str(use_ref))
    log.info('Reduce image at all = '+str(use_image))
    log.info('Report: '+report)

    return use_phot, use_ref, use_image, report

def append_errors(report,error):

    if len(report) == 0:

        report = error

    else:

        report += ', '+error

    return error


def verify_stage1_output(setup,log):
    """Function to verify that stage 0 has produced the expected output.

    This function checks for the presences of a metadata file and a stage log
    """

    log.info('Verifying stage 1 data products:')

    status = 'OK'
    report = 'Completed successfully'

    stage_log = os.path.join(setup.red_dir, 'stage1.log')

    if os.path.isfile(stage_log) == False:

        status = 'ERROR'
        report = 'Stage 0 finished without producing its stage log'

        log.info('Status: '+status)
        log.info('Report: '+report)

        return status, report

    reduction_metadata = metadata.MetaData()
    reduction_metadata.load_a_layer_from_file( setup.red_dir,
                                              'pyDANDIA_metadata.fits',
                                              'images_stats' )

    image_stats = reduction_metadata.images_stats[1]

    for flag in image_stats['USE_PHOT'].data:

        if flag != 0 and flag != 1:

            status = 'ERROR'
            report = 'Stage 1 produced unrecognised values in the metadata image stats table'

            log.info('Status: '+status)
            log.info('Report: '+report)

            return status, report

    log.info('Status: '+status)
    log.info('Report: '+report)

    return status, report

def verify_telescope_pointing(image_header):
    """Function to compare the CAT-RA, CAT-DEC requested for an observation with the
    RA, DEC of the telescopes pointing.  Images with a discrepancy greater than 1 arcmin
    are flagged as bad

    Input:
        :param image_header FITS image header object

    Output:
        :param image_status Boolean: Flag indicating whether the image passes
                                     the QC test
    """

    threshold = (5.0/60.0) * u.deg

    if 'N/A' not in image_header['CAT-RA'] and 'N/A' not in image_header['CAT-DEC']:
        requested_pointing = SkyCoord(image_header['CAT-RA']+' '+image_header['CAT-DEC'],
                                      frame='icrs', unit=(u.hourangle, u.deg))

        actual_pointing = SkyCoord(image_header['RA']+' '+image_header['DEC'],
                                      frame='icrs', unit=(u.hourangle, u.deg))

        if requested_pointing.separation(actual_pointing) <= threshold:
            return True
        else:
            return False

    else:
        # If this is true, assume the data were taken of a non-sidereal object
        return True

def verify_image_shifts(new_images, shift_data, image_red_status,threshold = 100.0, log=None):
    """Function to review the measured pixel offsets of each image from the
    reference for that dataset, and ensure that any severely offset images
    are marked as bad.  These images are removed from the new_images list.

    Inputs:
        :param list new_images: list of image names to process
        :param list shift_data: list of measured image shifts
        :param dict image_red_status: Reduction status of each image for the
                                      current reduction stage
    Outputs:
        :param dict image_red_status:
    """



    for i,entry in enumerate(shift_data):
        image_list = np.array(new_images)
        image = entry[0]
        if entry[1] == None or entry[2] == None or \
            abs(entry[1]) >= float(threshold) or abs(entry[2]) >= float(threshold):
            image_red_status[image] = '-1'

            idx = np.where(image_list == image)
            if len(idx[0]) > 0:
                rm_image = new_images.pop(idx[0][0])
                if log != None:
                    log.info('QC removed image '+rm_image+\
                        ' from processing list due to excessive pixel offset')

    return new_images, image_red_status

def verify_mask_statistics(reduction_metadata,image_name, mask_data, log=None):
    """Function to calculate basic statistical properties of a mask image
    to verify that they are within tolerances.
    Note: built-in threshold should only be applied to the fullframe image"""

    if 'QC_MAX_BAD_PIXEL' in reduction_metadata.reduction_parameters[1].keys():
        threshold = reduction_metadata.reduction_parameters[1]['QC_MAX_BAD_PIXEL']
    else:
        threshold = 2.0 # % of pixels in the full frame

    idx = np.where(mask_data != 0)
    npix = mask_data.shape[0]*mask_data.shape[1]
    n_bad = len(idx[0])
    percent_bad = (float(len(idx[0]))/float(npix))*100.0

#    (hist,bins) = np.histogram(mask_data)
#    jdx = np.where(bins.astype(int) <= 1.0)
#    j1 = jdx[0][-2]

    jdx = np.where(mask_data.astype(int) == 0)
    j1 = len(jdx[0])

    if log!=None:
        log.info('Verifying BPM for image '+image_name+':')
        log.info('BPM has '+str(n_bad)+' pixels flagged as bad, '+str(round(percent_bad,1))+'%')
        log.info('BPM has '+str(j1)+' pixels flagged as 0')

    if percent_bad < threshold:
        return True
    else:
        if log!=None:
            log.info('--> WARNING: Mask statistics indicate a problem')
        return False

def calc_phot_qc_metrics(photometry,site,n_selection=5000):
    """Function to calculate the timeseries photometric quality metrics.
    Based on code by Markus Hundertmark"""

    # For speed, a random selection of stars is chosen:
    n_stars = photometry.shape[0]
    random_index_array = (np.random.random(n_selection)*n_stars).astype(np.int)
    random_index_array.sort()

    metrics = []

    for index in random_index_array:
        mask = (photometry[index,:,13] > 0) & (np.isfinite(photometry[index,:,13]))
        (mean, medi, std) = sigma_clipped_stats(photometry[index,:,13][mask])
        if np.isfinite(medi):
            entry = [mean,medi,std,\
                    np.median(photometry[index,:,14][mask]),
                    len(photometry[index,:,14][mask]),
                    np.median(photometry[index,:,19][mask]),
                    np.median(photometry[index,:,20][mask]),
                    np.median(photometry[index,:,21][mask]),
                    np.median(photometry[index,:,22][mask]),
                    site]
            metrics.append(entry)
    metrics = np.array(metrics)

    table_data = [  Column(name='mean_cal_mag', data=metrics[:,0]),
                    Column(name='median_cal_mag', data=metrics[:,1]),
                    Column(name='std_dev_cal_mag', data=metrics[:,2]),
                    Column(name='median_cal_mag_error', data=metrics[:,3]),
                    Column(name='n_valid_points', data=metrics[:,4]),
                    Column(name='median_ps_factor', data=metrics[:,5]),
                    Column(name='median_ps_error', data=metrics[:,6]),
                    Column(name='median_sky_background', data=metrics[:,7]),
                    Column(name='median_sky_background_error', data=metrics[:,8]),
                    Column(name='site', data=metrics[:,9]) ]
    metrics = Table(data=table_data)

    return metrics
