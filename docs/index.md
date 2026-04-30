# nmtc-mapper 🗺️

**Automated NMTC eligibility checker for addresses and census tracts.**

Pass a DataFrame of 10,000 addresses and get back NMTC eligibility,
distress level, poverty rate, and AMI ratio — using official CDFI Fund
and Census Bureau data. No manual lookups required.

## Installation

    pip install nmtc-mapper

## Why nmtc-mapper?

The CDFI Fund provides a manual web tool (CIMS) for checking NMTC eligibility
one address at a time. nmtc-mapper automates this — pass 10,000 addresses
and get results in seconds using async batch geocoding.

## Key Features

- Async batch geocoding — processes 10,000 addresses with asyncio and aiohttp
- Rate limiting — respects Census API limits with semaphore control
- Retry logic — exponential backoff on failed requests
- Distress levels — deep, severe, LIC, and ineligible classifications
- Official data — uses CDFI Fund 2016-2020 ACS eligibility file
- Zero API keys — Census Bureau Geocoding API is completely free
