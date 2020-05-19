"""
    OpenID Connect relying party (RP) utilities
    ===========================================

    This modules defines utilities allowing to manipulate ID tokens and other common helpers.

"""

import logging
import datetime as dt
from calendar import timegm
from urllib.parse import urlparse, urljoin

from django.core.exceptions import SuspiciousOperation
from django.utils.encoding import force_bytes, smart_bytes
from jwkest import JWKESTException
from jwkest.jwk import KEYS
from jwkest.jws import JWS

from .conf import settings as oidc_rp_settings


def get_logger(name=''):
    return logging.getLogger('jumpserver.{}'.format(name))


logger = get_logger(__file__)


def validate_and_return_id_token(jws, nonce=None, validate_nonce=True):
    """ Validates the id_token according to the OpenID Connect specification. """
    log_prompt = "Validate ID Token: {}"
    logger.debug(log_prompt.format('Get shared key'))
    shared_key = oidc_rp_settings.CLIENT_SECRET \
        if oidc_rp_settings.PROVIDER_SIGNATURE_ALG == 'HS256' \
        else oidc_rp_settings.PROVIDER_SIGNATURE_KEY  # RS256

    try:
        # Decodes the JSON Web Token and raise an error if the signature is invalid.
        logger.debug(log_prompt.format('Verify compact jwk'))
        id_token = JWS().verify_compact(force_bytes(jws), _get_jwks_keys(shared_key))
    except JWKESTException as e:
        logger.debug(log_prompt.format('Verify compact jwkest exception: {}'.format(str(e))))
        return

    # Validates the claims embedded in the id_token.
    logger.debug(log_prompt.format('Validate claims'))
    _validate_claims(id_token, nonce=nonce, validate_nonce=validate_nonce)

    return id_token


def _get_jwks_keys(shared_key):
    """ Returns JWKS keys used to decrypt id_token values. """
    # The OpenID Connect Provider (OP) uses RSA keys to sign/enrypt ID tokens and generate public
    # keys allowing to decrypt them. These public keys are exposed through the 'jwks_uri' and should
    # be used to decrypt the JWS - JSON Web Signature.
    log_prompt = "Get jwks keys: {}"
    logger.debug(log_prompt.format('Start'))
    jwks_keys = KEYS()
    logger.debug(log_prompt.format('Load from provider jwks endpoint'))
    jwks_keys.load_from_url(oidc_rp_settings.PROVIDER_JWKS_ENDPOINT)
    # Adds the shared key (which can correspond to the client_secret) as an oct key so it can be
    # used for HMAC signatures.
    logger.debug(log_prompt.format('Add key'))
    jwks_keys.add({'key': smart_bytes(shared_key), 'kty': 'oct'})
    logger.debug(log_prompt.format('End'))
    return jwks_keys


def _validate_claims(id_token, nonce=None, validate_nonce=True):
    """ Validates the claims embedded in the JSON Web Token. """
    log_prompt = "Validate claims: {}"
    logger.debug(log_prompt.format('Start'))

    iss_parsed_url = urlparse(id_token['iss'])
    provider_parsed_url = urlparse(oidc_rp_settings.PROVIDER_ENDPOINT)
    if iss_parsed_url.netloc != provider_parsed_url.netloc:
        logger.debug(log_prompt.format('Invalid issuer'))
        raise SuspiciousOperation('Invalid issuer')

    if isinstance(id_token['aud'], str):
        id_token['aud'] = [id_token['aud']]

    if oidc_rp_settings.CLIENT_ID not in id_token['aud']:
        logger.debug(log_prompt.format('Invalid audience'))
        raise SuspiciousOperation('Invalid audience')

    if len(id_token['aud']) > 1 and 'azp' not in id_token:
        logger.debug(log_prompt.format('Incorrect id_token: azp'))
        raise SuspiciousOperation('Incorrect id_token: azp')

    if 'azp' in id_token and id_token['azp'] != oidc_rp_settings.CLIENT_ID:
        raise SuspiciousOperation('Incorrect id_token: azp')

    utc_timestamp = timegm(dt.datetime.utcnow().utctimetuple())
    if utc_timestamp > id_token['exp']:
        logger.debug(log_prompt.format('Signature has expired'))
        raise SuspiciousOperation('Signature has expired')

    if 'nbf' in id_token and utc_timestamp < id_token['nbf']:
        logger.debug(log_prompt.format('Incorrect id_token: nbf'))
        raise SuspiciousOperation('Incorrect id_token: nbf')

    # Verifies that the token was issued in the allowed timeframe.
    if utc_timestamp > id_token['iat'] + oidc_rp_settings.ID_TOKEN_MAX_AGE:
        logger.debug(log_prompt.format('Incorrect id_token: iat'))
        raise SuspiciousOperation('Incorrect id_token: iat')

    # Validate the nonce to ensure the request was not modified if applicable.
    id_token_nonce = id_token.get('nonce', None)
    if validate_nonce and oidc_rp_settings.USE_NONCE and id_token_nonce != nonce:
        logger.debug(log_prompt.format('Incorrect id_token: nonce'))
        raise SuspiciousOperation('Incorrect id_token: nonce')

    logger.debug(log_prompt.format('End'))


def build_absolute_uri(request, path=None):
    """
    Build absolute redirect uri
    """
    if path is None:
        path = '/'

    if oidc_rp_settings.BASE_SITE_URL:
        redirect_uri = urljoin(oidc_rp_settings.BASE_SITE_URL, path)
    else:
        redirect_uri = request.build_absolute_uri(path)
    return redirect_uri
