#!/usr/bin/env python3
"""
Download the latest OpenAI Codex App MSIX package from Microsoft Store FE3 services.
Based on StoreLib (MPL-2.0) and microsoft-store-package-downloader-skill logic.
Run on macOS/Linux/Windows with Python 3.10+.
"""
import argparse
import base64
import hashlib
import json
import os
import re
import sys
import time
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import unquote

import ssl
import urllib.request

# Some sandbox/proxy environments cannot verify Microsoft's FE3 cert chain;
# use an unverified context for all Microsoft Store HTTPS calls.
_UNVERIFIED_SSL_CONTEXT = ssl._create_unverified_context()

PRODUCT_ID = "9PLM9XGG6VKS"
DELIVERY_ENDPOINT = "https://fe3.delivery.mp.microsoft.com/ClientWebService/client.asmx"
SECURED_DELIVERY_ENDPOINT = f"{DELIVERY_ENDPOINT}/secured"
CATALOG_ENDPOINT = "https://displaycatalog.mp.microsoft.com/v7.0/products"
USER_AGENT = "StoreLib"
DOWNLOAD_USER_AGENT = "Microsoft-Delivery-Optimization/10.0"

# Device token from StoreLib FE3Handler.cs (MPL-2.0)
DEVICE_TOKEN = (
    "<Device>dAA9AEUAdwBBAHcAQQBzAE4AMwBCAEEAQQBVADEAYgB5AHMAZQBtAGIAZQBEAFYAQwArADMAZgBtADcAbwBXAHkASAA3AGIAbgBnAEcAWQBtAEEAQQBMAGoAbQBqAFYAVQB2AFEAYwA0AEsAVwBFAC8AYwBDAEwANQBYAGUANABnAHYAWABkAGkAegBHAGwAZABjADEAZAAvAFcAeQAvAHgASgBQAG4AVwBRAGUAYwBtAHYAbwBjAGkAZwA5AGoAZABwAE4AawBIAG0AYQBzAHAAVABKAEwARAArAFAAYwBBAFgAbQAvAFQAcAA3AEgAagBzAEYANAA0AEgAdABsAC8AMQBtAHUAcgAwAFMAdQBtAG8AMABZAGEAdgBqAFIANwArADQAcABoAC8AcwA4ADEANgBFAFkANQBNAFIAbQBnAFIAQwA2ADMAQwBSAEoAQQBVAHYAZgBzADQAaQB2AHgAYwB5AEwAbAA2AHoAOABlAHgAMABrAFgAOQBPAHcAYQB0ADEAdQBwAFMAOAAxAEgANgA4AEEASABzAEoAegBnAFQAQQBMAG8AbgBBADIAWQBBAEEAQQBpAGcANQBJADMAUQAvAFYASABLAHcANABBAEIAcQA5AFMAcQBhADEAQgA4AGsAVQAxAGEAbwBLAEEAdQA0AHYAbABWAG4AdwBWADMAUQB6AHMATgBtAEQAaQBqAGgANQBkAEcAcgBpADgAQQBlAEUARQBWAEcAbQBXAGgASQBCAE0AUAAyAEQAVwA0ADMAZABWAGkARABUAHoAVQB0AHQARQBMAEgAaABSAGYAcgBhAGIAWgBsAHQAQQBUAEUATABmAHMARQBGAFUAYQBRAFMASgB4ADUAeQBRADgAagBaAEUAZQAyAHgANABCADMAMQB2AEIAMgBqAC8AUgBLAGEAWQAvAHEAeQB0AHoANwBUAHYAdAB3AHQAagBzADYAUQBYAEIAZQA4AHMAZwBJAG8AOQBiADUAQQBCADcAOAAxAHMANgAvAGQAUwBFAHgATgBEAEQAYQBRAHoAQQBYAFAAWABCAFkAdQBYAFEARQBzAE8AegA4AHQAcgBpAGUATQBiAEIAZQBUAFkAOQBiAG8AQgBOAE8AaQBVADcATgBSAEYAOQAzAG8AVgArAFYAQQBiAGgAcAAwAHAAUgBQAFMAZQBmAEcARwBPAHEAdwBTAGcANwA3AHMAaAA5AEoASABNAHAARABNAFMAbgBrAHEAcgAyAGYARgBpAEMAUABrAHcAVgBvAHgANgBuAG4AeABGAEQAbwBXAC8AYQAxAHQAYQBaAHcAegB5AGwATABMADEAMgB3AHUAYgBtADUAdQBtAHAAcQB5AFcAYwBLAFIAagB5AGgAMgBKAFQARgBKAFcANQBnAFgARQBJADUAcAA4ADAARwB1ADIAbgB4AEwAUgBOAHcAaQB3AHIANwBXAE0AUgBBAFYASwBGAFcATQBlAFIAegBsADkAVQBxAGcALwBwAFgALwB2AGUATAB3AFMAawAyAFMAUwBIAGYAYQBLADYAagBhAG8AWQB1AG4AUgBHAHIAOABtAGIARQBvAEgAbABGADYASgBDAGEAYQBUAEIAWABCAGMAdgB1AGUAQwBKAG8AOQA4AGgAUgBBAHIARwB3ADQAKwBQAEgAZQBUAGIATgBTAEUAWABYAHoAdgBaADYAdQBXADUARQBBAGYAZABaAG0AUwA4ADgAVgBKAGMAWgBhAEYASwA3AHgAeABnADAAdwBvAG4ANwBoADAAeABDADYAWgBCADAAYwBZAGoATAByAC8ARwBlAE8AegA5AEcANABRAFUASAA5AEUAawB5ADAAZAB5AEYALwByAGUAVQAxAEkAeQBpAGEAcABwAGgATwBQADgAUwAyAHQANABCAHIAUABaAFgAVAB2AEMAMABQADcAegBPACsAZgBHAGsAeABWAG0AKwBVAGYAWgBiAFEANQA1AHMAdwBFAD0AJgBwAD0A</Device>"
)


SOAP_NAMESPACES = {
    "soap": "http://www.w3.org/2003/05/soap-envelope",
    "wsa": "http://www.w3.org/2005/08/addressing",
    "wse": "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd",
    "wsu": "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd",
    "wuws": "http://schemas.microsoft.com/msus/2014/10/WindowsUpdateAuthorization",
    "sd": "http://www.microsoft.com/SoftwareDistribution/Server/ClientWebService",
}


def soap_request(url: str, body: str, secured: bool = False) -> str:
    """Send a SOAP request and return decoded text."""
    req = urllib.request.Request(
        url,
        data=body.encode("utf-8"),
        headers={
            "Content-Type": "application/soap+xml; charset=utf-8",
            "User-Agent": USER_AGENT,
            "MS-CV": f"{uuid.uuid4().hex}.1",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60, context=_UNVERIFIED_SSL_CONTEXT) as resp:
        raw = resp.read()
        # Some responses are HTML-encoded XML
        text = raw.decode("utf-8")
        text = text.replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"').replace("&amp;", "&")
        return text


def get_cookie() -> str:
    """Obtain an encrypted FE3 cookie."""
    body = """<Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns="http://www.w3.org/2003/05/soap-envelope">
  <Header>
    <Action d3p1:mustUnderstand="1" xmlns:d3p1="http://www.w3.org/2003/05/soap-envelope" xmlns="http://www.w3.org/2005/08/addressing">http://www.microsoft.com/SoftwareDistribution/Server/ClientWebService/GetCookie</Action>
    <MessageID xmlns="http://www.w3.org/2005/08/addressing">urn:uuid:""" + str(uuid.uuid4()) + """</MessageID>
    <To d3p1:mustUnderstand="1" xmlns:d3p1="http://www.w3.org/2003/05/soap-envelope" xmlns="http://www.w3.org/2005/08/addressing">https://fe3.delivery.mp.microsoft.com/ClientWebService/client.asmx</To>
    <Security d3p1:mustUnderstand="1" xmlns:d3p1="http://www.w3.org/2003/05/soap-envelope" xmlns="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd">
      <Timestamp xmlns="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd">
        <Created>2017-12-02T00:16:15.210Z</Created>
        <Expires>2017-12-29T06:25:43.943Z</Expires>
      </Timestamp>
      <WindowsUpdateTicketsToken d4p1:id="ClientMSA" xmlns:d4p1="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd" xmlns="http://schemas.microsoft.com/msus/2014/10/WindowsUpdateAuthorization">
        <TicketType Name="MSA" Version="1.0" Policy="MBI_SSL">
          <User />
        </TicketType>
      </WindowsUpdateTicketsToken>
    </Security>
  </Header>
  <Body>
    <GetCookie xmlns="http://www.microsoft.com/SoftwareDistribution/Server/ClientWebService">
      <oldCookie>
      </oldCookie>
      <lastChange>2015-10-21T17:01:07.1472913Z</lastChange>
      <currentTime>2017-12-02T00:16:15.217Z</currentTime>
      <protocolVersion>1.40</protocolVersion>
    </GetCookie>
  </Body>
</Envelope>"""
    resp = soap_request(DELIVERY_ENDPOINT, body)
    root = ET.fromstring(resp)
    encrypted = root.find(".//sd:EncryptedData", SOAP_NAMESPACES)
    if encrypted is None or not encrypted.text:
        raise RuntimeError("FE3 did not return an encrypted cookie.")
    return encrypted.text


SD_NS = "{http://www.microsoft.com/SoftwareDistribution/Server/ClientWebService}"


def sync_updates(cookie: str, wu_category_id: str) -> tuple[list[str], list[str], list[str]]:
    """Return (update_ids, revision_ids, package_monikers)."""
    with open(Path(__file__).parent / "WUIDRequest.xml", "r", encoding="utf-8") as f:
        template = f.read()
    body = template.format(cookie, wu_category_id, DEVICE_TOKEN)
    resp = soap_request(DELIVERY_ENDPOINT, body)

    # HTML decode again in case
    resp = (
        resp.replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&amp;", "&")
    )
    root = ET.fromstring(resp)

    # Build a parent map so we can trace SecuredFragment -> Properties -> Xml -> Update.
    parent_map = {c: p for p in root.iter() for c in p}

    update_ids, revision_ids, monikers = [], [], []

    # The downloadable packages are inside <NewUpdates>/<UpdateInfo>/<Xml>.
    for update_info in root.iter(f"{SD_NS}UpdateInfo"):
        xml_node = update_info.find(f"{SD_NS}Xml")
        if xml_node is None:
            continue

        # Must contain a SecuredFragment to have a downloadable package URL.
        if xml_node.find(f".//{SD_NS}SecuredFragment") is None:
            continue

        identity = xml_node.find(f"{SD_NS}UpdateIdentity")
        if identity is None:
            continue

        metadata = xml_node.find(f".//{SD_NS}AppxMetadata")

        update_ids.append(identity.attrib.get("UpdateID", ""))
        revision_ids.append(identity.attrib.get("RevisionNumber", ""))
        monikers.append(
            metadata.attrib.get("PackageMoniker", update_ids[-1])
            if metadata is not None
            else update_ids[-1]
        )

    return update_ids, revision_ids, monikers


def get_file_urls(update_id: str, revision_id: str) -> list[str]:
    """Get download URLs for an update ID."""
    with open(Path(__file__).parent / "FE3FileUrl.xml", "r", encoding="utf-8") as f:
        template = f.read()
    body = template.format(update_id, revision_id, DEVICE_TOKEN)
    resp = soap_request(SECURED_DELIVERY_ENDPOINT, body, secured=True)
    # Some FE3 responses contain unescaped '&' inside URLs. Escape them while
    # preserving existing XML entities.
    resp = re.sub(
        r"&(?!amp;|lt;|gt;|quot;|apos;|#[0-9]+;|#x[0-9a-fA-F]+;)",
        "&amp;",
        resp,
    )
    root = ET.fromstring(resp)
    urls = []
    for location in root.findall(".//sd:FileLocation", SOAP_NAMESPACES):
        for child in location:
            if child.tag.endswith("Url"):
                url = child.text or ""
                # Filter out blockmap URLs (commonly 99 chars) and empty
                if len(url) > 100 and "blockmap" not in url.lower():
                    urls.append(url)
    return urls


def get_wu_category_id(product_id: str, market: str = "US", language: str = "en") -> tuple[str, str, str, str]:
    """Query display catalog and return (WuCategoryId, PackageIdentityName, Title, Publisher)."""
    url = (
        f"{CATALOG_ENDPOINT}/{product_id}"
        f"?market={market}&languages={language}-{market},{language},neutral"
    )
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30, context=_UNVERIFIED_SSL_CONTEXT) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    product = data.get("Product") or data["Products"][0]
    sku = next(
        (s for s in product.get("DisplaySkuAvailabilities", []) if s.get("Sku", {}).get("Properties", {}).get("FulfillmentData")),
        None,
    )
    if sku is None:
        raise RuntimeError("Product does not expose downloadable package fulfillment data.")

    wu_cat_id = sku["Sku"]["Properties"]["FulfillmentData"]["WuCategoryId"]
    package_identity = product["Properties"]["PackageIdentityName"]
    title = product["LocalizedProperties"][0]["ProductTitle"]
    publisher = product["LocalizedProperties"][0]["PublisherName"]
    return wu_cat_id, package_identity, title, publisher


def safe_filename(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', "_", name)


def download_file(url: str, dest: Path) -> None:
    """Download a file using curl (memory-efficient, supports resume)."""
    import subprocess
    import shutil

    temp = dest.with_suffix(dest.suffix + ".download")
    existing_size = temp.stat().st_size if temp.exists() else 0
    if existing_size > 0:
        print(f"            Resuming from {existing_size} bytes...")

    curl_bin = shutil.which("curl")
    if not curl_bin:
        raise RuntimeError("curl not found in PATH")

    args = [
        curl_bin,
        "-L",
        "-k",  # skip SSL verification (sandbox proxy)
        "-C", "-",  # resume
        "-o", str(temp),
        "--retry", "3",
        "--retry-delay", "5",
        "-H", f"User-Agent: {DOWNLOAD_USER_AGENT}",
        "--compressed",
        url,
    ]
    result = subprocess.run(args, timeout=580, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"curl failed (exit {result.returncode}): {result.stderr}")

    temp.rename(dest)


def main():
    parser = argparse.ArgumentParser(description="Download OpenAI Codex App MSIX from Microsoft Store")
    parser.add_argument("--product-id", default=PRODUCT_ID)
    parser.add_argument("--market", default="US")
    parser.add_argument("--language", default="en")
    parser.add_argument("--architecture", default="x64", choices=["x64", "x86", "arm64", "arm", "all"])
    parser.add_argument("--output", default="./microsoft-store-downloads")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    out_dir = Path(args.output).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    # Write XML templates next to script if not present
    for tpl_name in ["WUIDRequest.xml", "FE3FileUrl.xml"]:
        tpl_path = Path(__file__).parent / tpl_name
        if not tpl_path.exists():
            raise FileNotFoundError(f"Missing template: {tpl_path}")

    print(f"[1/5] Querying Microsoft Store catalog for {args.product_id} ...")
    wu_cat_id, package_identity, title, publisher = get_wu_category_id(
        args.product_id, args.market, args.language
    )
    print(f"      Title: {title}")
    print(f"      Publisher: {publisher}")
    print(f"      PackageIdentityName: {package_identity}")
    print(f"      WuCategoryId: {wu_cat_id}")

    print("[2/5] Obtaining FE3 cookie ...")
    cookie = get_cookie()
    print("      Cookie obtained.")

    print("[3/5] Syncing updates ...")
    update_ids, revision_ids, monikers = sync_updates(cookie, wu_cat_id)
    print(f"      Found {len(update_ids)} update package(s).")

    # If --print-urls is set, just print URLs and exit
    if os.environ.get("PRINT_URLS_ONLY"):
        for uid, rev, moniker in zip(update_ids, revision_ids, monikers):
            urls = get_file_urls(uid, rev)
            for url in urls:
                if "delivery.mp.microsoft.com" not in url:
                    continue
                print(f"{url}")
        return

    print("[4/5] Resolving download URLs ...")
    candidates = []
    for uid, rev, moniker in zip(update_ids, revision_ids, monikers):
        urls = get_file_urls(uid, rev)
        for url in urls:
            # Basic host check
            if "delivery.mp.microsoft.com" not in url:
                print(f"      Skipping unexpected host: {url}")
                continue
            candidates.append((url, moniker))
    print(f"      Resolved {len(candidates)} candidate URL(s).")

    print("[5/5] Filtering and downloading packages ...")
    wanted = args.architecture
    downloaded = []
    seen = set()

    for url, moniker in candidates:
        # Try to get filename from Content-Disposition via HEAD
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": DOWNLOAD_USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=30, context=_UNVERIFIED_SSL_CONTEXT) as resp:
                cd = resp.headers.get("Content-Disposition", "")
                length = resp.headers.get("Content-Length")
        except Exception as e:
            print(f"      HEAD failed for {url}: {e}")
            continue

        filename = None
        m = re.search(r"filename\*=UTF-8''([^;]+)", cd)
        if m:
            filename = unquote(m.group(1))
        else:
            m = re.search(r'filename="?([^";]+)"?', cd)
            if m:
                filename = m.group(1)
        if not filename:
            filename = f"{moniker}.msix"
        filename = safe_filename(filename)

        ext = Path(filename).suffix.lower()
        if ext not in {".msix", ".msixbundle", ".appx", ".appxbundle", ".eappx", ".emsix"}:
            print(f"      Skipping non-package file: {filename}")
            continue

        # Architecture filter
        if wanted != "all":
            arch_match = re.search(r"_(x64|x86|arm64|arm|neutral)_", filename, re.I)
            if arch_match:
                arch = arch_match.group(1).lower()
                if arch != "neutral" and arch != wanted:
                    print(f"      Skipping architecture mismatch: {filename}")
                    continue

        if filename in seen:
            continue
        seen.add(filename)

        dest = out_dir / filename
        if dest.exists() and not args.force:
            print(f"      Already exists (skip): {filename}")
            continue

        print(f"      Downloading {filename} ({length or '?'} bytes) ...")
        download_file(url, dest)
        sha256 = hashlib.sha256(dest.read_bytes()).hexdigest()
        downloaded.append({
            "FileName": filename,
            "Path": str(dest),
            "Bytes": dest.stat().st_size,
            "Sha256": sha256,
            "SourceUrl": url,
        })

    if not downloaded:
        print("No packages were downloaded.")
        sys.exit(1)

    manifest = {
        "ProductId": args.product_id.upper(),
        "Title": title,
        "Publisher": publisher,
        "PackageIdentityName": package_identity,
        "Architecture": args.architecture,
        "DownloadedAtUtc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "Packages": downloaded,
    }
    manifest_path = out_dir / "package-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    # Generate install.ps1
    install_ps1 = out_dir / "install.ps1"
    install_ps1.write_text(
        '''$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$manifest = Get-Content -Raw -LiteralPath (Join-Path $root "package-manifest.json") | ConvertFrom-Json
$packages = @($manifest.Packages | ForEach-Object { Get-Item -LiteralPath (Join-Path $root $_.FileName) })
$main = $packages | Where-Object { $_.Name -like "$($manifest.PackageIdentityName)_*" } | Select-Object -First 1
if ($null -eq $main) { throw "The main application package was not found." }
$dependencies = @($packages | Where-Object FullName -ne $main.FullName)
if ($dependencies.Count -gt 0) {
    Add-AppxPackage -Path $main.FullName -DependencyPath $dependencies.FullName
} else {
    Add-AppxPackage -Path $main.FullName
}
Write-Host "$($manifest.Title) installed successfully."
''',
        encoding="utf-8",
    )

    print(f"\nDone. Downloaded {len(downloaded)} package(s) to {out_dir}")
    for d in downloaded:
        print(f"  - {d['FileName']} ({d['Bytes']} bytes, SHA256: {d['Sha256']})")
    print(f"\nManifest: {manifest_path}")
    print(f"Install script: {install_ps1}")


if __name__ == "__main__":
    main()
