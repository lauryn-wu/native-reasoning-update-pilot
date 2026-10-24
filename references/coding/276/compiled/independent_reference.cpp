// Independently authored exact reference for the finite published suite.
// Execute/compile only inside the pinned offline Docker construction runner.
// Deliberately uses a plain square table and split-or-enclose recurrence,
// independently of the optimized packed row/column implementation.
#include <algorithm>
#include <cstdint>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>

using U64 = std::uint64_t;

U64 solve(const std::vector<std::int64_t>& a) {
    const std::size_t n = a.size();
    if (n < 2) return 0;
    const auto [lo, hi] = std::minmax_element(a.begin(), a.end());
    // Unsigned subtraction is defined modulo2^64 and gives the exact
    // nonnegative distance between any two signed64 values in sorted order.
    const U64 span = U64(*hi) - U64(*lo);
    if (span && n / 2 > std::numeric_limits<U64>::max() / span)
        throw std::overflow_error("Independent checker total exceeds uint64");
    if (n > std::numeric_limits<std::size_t>::max() / n ||
        n * n > std::numeric_limits<std::size_t>::max() / sizeof(U64))
        throw std::overflow_error("Independent table allocation size overflow");
    std::vector<U64> table(n * n, 0);
    auto at = [&](std::size_t l, std::size_t r) -> U64& { return table[l*n+r]; };
    auto distance = [](std::int64_t x, std::int64_t y) -> U64 {
        return x >= y ? U64(x) - U64(y) : U64(y) - U64(x);
    };
    for (std::size_t length = 2; length <= n; length += 2) {
        for (std::size_t left = 0; left + length <= n; ++left) {
            const std::size_t right = left + length - 1;
            // An indecomposable noncrossing matching pairs the endpoints.
            U64 best = distance(a[left], a[right]);
            if (length > 2) best += at(left + 1, right - 1);
            // Otherwise its first component ends at an even-length prefix.
            for (std::size_t cut = left + 1; cut < right; cut += 2)
                best = std::min(best, at(left, cut) + at(cut + 1, right));
            at(left, right) = best;
        }
    }
    if (n % 2 == 0) return at(0, n - 1);
    U64 best = at(1, n - 1);
    for (std::size_t survivor = 2; survivor < n; survivor += 2) {
        U64 value = at(0, survivor - 1);
        if (survivor + 1 < n) value += at(survivor + 1, n - 1);
        best = std::min(best, value);
    }
    return best;
}

int main(int argc, char** argv) {
    try {
        std::ios::sync_with_stdio(false); std::cin.tie(nullptr);
        const bool batch = argc == 2 && std::string(argv[1]) == "--batch";
        if (argc > 1 && !batch) throw std::invalid_argument("Unsupported option");
        std::size_t count = 1;
        if (batch && !(std::cin >> count)) throw std::invalid_argument("Missing count");
        for (std::size_t index = 0; index < count; ++index) {
            std::size_t n;
            if (!(std::cin >> n)) throw std::invalid_argument("Missing length");
            std::vector<std::int64_t> a(n);
            for (auto& value : a)
                if (!(std::cin >> value)) throw std::invalid_argument("Non-int64 input");
            std::cout << solve(a) << '\n';
        }
        std::string extra;
        if (std::cin >> extra) throw std::invalid_argument("Trailing input");
        return 0;
    } catch (const std::exception& e) {
        std::cerr << e.what() << '\n';
        return 1;
    }
}
