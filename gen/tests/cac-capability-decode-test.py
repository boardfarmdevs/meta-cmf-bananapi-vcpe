#!/usr/bin/env python3
import argparse
import subprocess
import tempfile
from pathlib import Path


parser = argparse.ArgumentParser(description="Compile the production compact CAC decoder with guarded wire payloads")
parser.add_argument("source", type=Path)
args = parser.parse_args()
source = args.source.read_text()
start = source.index("static bool decode_cac_capability(")
end = source.index("\nint em_capability_t::handle_ap_cap_report(", start)
harness = r'''
#include <cassert>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <vector>
#include <sys/mman.h>
#include <unistd.h>
using mac_address_t = unsigned char[6];
constexpr unsigned int EM_MAX_RADIO_PER_AGENT = 4;
constexpr unsigned int EM_MAX_CAC_METHODS = 4;
struct __attribute__((packed)) em_cac_op_class_t {
    unsigned char op_class, num, channels[16];
};
struct __attribute__((packed)) em_cac_cap_method_t {
    unsigned char cac_method;
    unsigned int cac_duration : 24;
    unsigned char op_classes_num;
    em_cac_op_class_t op_classes[48];
};
struct __attribute__((packed)) em_cac_cap_radio_t {
    mac_address_t ruid;
    unsigned char cac_methods_num;
    em_cac_cap_method_t cac_methods[EM_MAX_CAC_METHODS];
};
struct __attribute__((packed)) em_cac_cap_t {
    unsigned short country_code;
    unsigned char radios_num;
    em_cac_cap_radio_t radios[EM_MAX_RADIO_PER_AGENT];
};
'''
harness += source[start:end]
harness += r'''
int main() {
    const std::vector<unsigned char> radio = {2,0,0,0,1,0, 1, 0,0x01,0x02,0x03,1, 121,2,100,104};
    std::vector<unsigned char> wire = {'U','S',2};
    wire.insert(wire.end(), radio.begin(), radio.end());
    wire.insert(wire.end(), radio.begin(), radio.end());
    wire[3 + radio.size() + 4] = 2;
    const size_t page_size = static_cast<size_t>(sysconf(_SC_PAGESIZE));
    auto *pages = static_cast<unsigned char *>(mmap(nullptr, page_size * 2,
        PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0));
    assert(pages != MAP_FAILED);
    assert(mprotect(pages + page_size, page_size, PROT_NONE) == 0);
    em_cac_cap_t decoded = {};
    for (size_t length = 0; length <= wire.size(); length++) {
        unsigned char *guarded = pages + page_size - length;
        memcpy(guarded, wire.data(), length);
        assert(decode_cac_capability(guarded, length, decoded) == (length == wire.size()));
    }
    assert(decoded.radios_num == 2);
    assert(decoded.radios[1].ruid[4] == 2);
    assert(decoded.radios[0].cac_methods[0].cac_duration == 0x010203);
    assert(decoded.radios[1].cac_methods[0].op_classes[0].channels[1] == 104);
    for (size_t index : {size_t(2), size_t(9), size_t(14), size_t(16)}) {
        auto oversized = wire;
        oversized[index] = 255;
        assert(!decode_cac_capability(oversized.data(), oversized.size(), decoded));
    }
    wire.push_back(0);
    assert(!decode_cac_capability(wire.data(), wire.size(), decoded));
    const unsigned char empty[] = {'U','S',0};
    assert(decode_cac_capability(empty, sizeof(empty), decoded));
    munmap(pages, page_size * 2);
    std::cout << "PASS compact multi-radio CAC, byte-order, every truncation, bounds and guard page\n";
}
'''
with tempfile.TemporaryDirectory(prefix="cac-capability-test-") as directory:
    root = Path(directory)
    translation_unit = root / "test.cpp"
    binary = root / "test"
    translation_unit.write_text(harness)
    subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-O2",
                    str(translation_unit), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
