# Lab override of exec_curl_mtls (dev/lab images only).
#
# The stock exec_curl_mtls (defined inline in uploadDumps.sh / uploadDumpsToS3.sh)
# performs an Xpki mTLS curl to the production crash portal. Those scripts
# "source $RDK_PATH/exec_curl_mtls.sh" when the file exists, which overrides the
# inline function. The lab SSR accepts the upload over TLS (stunnel, self-signed
# cert) or plain HTTP and needs no client cert, so we run the caller's curl args
# with plain curl plus -k (accept the self-signed cert).
#
# Both the sign request and the dump PUT pass their full curl arg string as $1
# (including -o <body-file> and -w "%{http_code} ..."). We run it and echo
# curl's exit code; the callers read the HTTP code back from /tmp/httpcode.
exec_curl_mtls() {
    eval /usr/bin/curl -k $1 > /tmp/httpcode 2>/dev/null
    echo $?
}
