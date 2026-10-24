// Exact initial/minimum reference for released source 276.
// Execute only in the pinned, bounded Docker construction environment.
// C++17; no nonstandard headers or libraries are required.
#include <algorithm>
#include <chrono>
#include <cstdint>
#include <iomanip>
#include <iostream>
#include <limits>
#include <new>
#include <numeric>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace {

// The recurrence needs only nonnegative addition, subtraction, and comparison.
// Base 10^9 limbs support exact decimal integers beyond any machine word width.
class Natural {
    static constexpr std::uint64_t base = 1000000000ULL;
    std::vector<std::uint32_t> limbs;  // Little endian; zero has no limbs.

    void normalize() {
        while (!limbs.empty() && limbs.back() == 0) limbs.pop_back();
    }

public:
    Natural() = default;

    static Natural decimal(const std::string& text, std::size_t begin) {
        if (begin == text.size()) throw std::runtime_error("missing integer digits");
        for (std::size_t i = begin; i < text.size(); ++i) {
            if (text[i] < '0' || text[i] > '9')
                throw std::runtime_error("nondecimal integer token");
        }
        Natural result;
        std::size_t end = text.size();
        while (end > begin) {
            const std::size_t start = end - begin > 9 ? end - 9 : begin;
            std::uint32_t limb = 0;
            for (std::size_t i = start; i < end; ++i)
                limb = limb * 10U + static_cast<std::uint32_t>(text[i] - '0');
            result.limbs.push_back(limb);
            end = start;
        }
        result.normalize();
        return result;
    }

    bool zero() const { return limbs.empty(); }

    bool as_u64(std::uint64_t& result) const {
        result = 0;
        for (std::size_t i = limbs.size(); i-- > 0;) {
            if (result > (std::numeric_limits<std::uint64_t>::max() - limbs[i]) / base)
                return false;
            result = result * base + limbs[i];
        }
        return true;
    }

    friend bool operator<(const Natural& a, const Natural& b) {
        if (a.limbs.size() != b.limbs.size()) return a.limbs.size() < b.limbs.size();
        for (std::size_t i = a.limbs.size(); i-- > 0;)
            if (a.limbs[i] != b.limbs[i]) return a.limbs[i] < b.limbs[i];
        return false;
    }

    Natural& operator+=(const Natural& other) {
        const std::size_t count = std::max(limbs.size(), other.limbs.size());
        limbs.resize(count, 0);
        std::uint64_t carry = 0;
        for (std::size_t i = 0; i < count; ++i) {
            const std::uint64_t total = static_cast<std::uint64_t>(limbs[i]) +
                (i < other.limbs.size() ? other.limbs[i] : 0U) + carry;
            limbs[i] = static_cast<std::uint32_t>(total % base);
            carry = total / base;
        }
        if (carry != 0) limbs.push_back(static_cast<std::uint32_t>(carry));
        return *this;
    }

    friend Natural operator+(Natural a, const Natural& b) { a += b; return a; }

    // Checked precondition; subtraction never represents a negative result.
    static Natural subtract(const Natural& a, const Natural& b) {
        if (a < b) throw std::runtime_error("internal negative natural subtraction");
        Natural result = a;
        std::int64_t borrow = 0;
        for (std::size_t i = 0; i < result.limbs.size(); ++i) {
            std::int64_t digit = static_cast<std::int64_t>(result.limbs[i]) -
                (i < b.limbs.size() ? static_cast<std::int64_t>(b.limbs[i]) : 0) - borrow;
            if (digit < 0) { digit += static_cast<std::int64_t>(base); borrow = 1; }
            else borrow = 0;
            result.limbs[i] = static_cast<std::uint32_t>(digit);
        }
        if (borrow != 0) throw std::runtime_error("internal subtraction borrow");
        result.normalize();
        return result;
    }

    friend std::ostream& operator<<(std::ostream& out, const Natural& value) {
        if (value.limbs.empty()) return out << '0';
        out << value.limbs.back();
        const char old_fill = out.fill('0');
        for (std::size_t i = value.limbs.size() - 1; i-- > 0;)
            out << std::setw(9) << value.limbs[i];
        out.fill(old_fill);
        return out;
    }
};

struct Integer {
    bool negative = false;
    Natural magnitude;

    static Integer decimal(const std::string& token) {
        if (token.empty()) throw std::runtime_error("empty integer token");
        const bool sign = token[0] == '-' || token[0] == '+';
        Integer value;
        value.magnitude = Natural::decimal(token, sign ? 1 : 0);
        value.negative = token[0] == '-' && !value.magnitude.zero();
        return value;
    }

    bool as_i64(std::int64_t& result) const {
        std::uint64_t value = 0;
        if (!magnitude.as_u64(value)) return false;
        const std::uint64_t negative_limit = std::uint64_t{1} << 63U;
        if (negative) {
            if (value > negative_limit) return false;
            result = value == negative_limit ? std::numeric_limits<std::int64_t>::min()
                                            : -static_cast<std::int64_t>(value);
        } else {
            if (value > static_cast<std::uint64_t>(std::numeric_limits<std::int64_t>::max()))
                return false;
            result = static_cast<std::int64_t>(value);
        }
        return true;
    }
};

Natural distance(const Integer& a, const Integer& b) {
    if (a.negative != b.negative) return a.magnitude + b.magnitude;
    return a.magnitude < b.magnitude ? Natural::subtract(b.magnitude, a.magnitude)
                                    : Natural::subtract(a.magnitude, b.magnitude);
}

std::uint64_t distance(std::int64_t a, std::int64_t b) {
    // Unsigned subtraction is exact modulo 2^64, and the mathematical distance
    // between two int64 values lies in [0, 2^64-1]. No signed subtraction occurs.
    return a >= b ? static_cast<std::uint64_t>(a) - static_cast<std::uint64_t>(b)
                  : static_cast<std::uint64_t>(b) - static_cast<std::uint64_t>(a);
}

std::string token(std::istream& in) {
    std::string result;
    if (!(in >> result)) throw std::runtime_error("missing input token");
    return result;
}

std::size_t size_token(std::istream& in) {
    const Integer value = Integer::decimal(token(in));
    std::uint64_t result = 0;
    if (value.negative || !value.magnitude.as_u64(result) ||
        result > std::numeric_limits<std::size_t>::max())
        throw std::runtime_error("nonnegative length is not representable");
    return static_cast<std::size_t>(result);
}

struct Layout {
    std::vector<std::size_t> row;
    std::vector<std::size_t> column;
    std::size_t cells = 0;

    explicit Layout(std::size_t n) {
        if (n == std::numeric_limits<std::size_t>::max())
            throw std::runtime_error("table dimension overflow");
        const std::size_t half = n / 2;
        const std::size_t rest = n - half;
        if (half != 0 && rest > std::numeric_limits<std::size_t>::max() / half)
            throw std::runtime_error("table cell count overflow");
        cells = half * rest;  // Number of nonempty even-length intervals.
        row.resize(n + 1, 0);
        column.resize(n + 1, 0);
        for (std::size_t i = 0; i < n; ++i) {
            row[i + 1] = row[i] + (n - i) / 2;
            column[i + 1] = column[i] + (i + 1) / 2;
        }
        if (row.back() != cells || column.back() != cells)
            throw std::runtime_error("internal packed table size mismatch");
    }
};

template<class Score, class Value>
Score exact_minimum(const std::vector<Value>& a) {
    const std::size_t n = a.size();
    if (n < 2) return Score{};
    const Layout layout(n);
    if (layout.cells > std::vector<Score>().max_size())
        throw std::runtime_error("table allocation size is not representable");
    std::vector<Score> rows(layout.cells);
    std::vector<Score> columns(layout.cells);
    for (std::size_t pairs = 1; pairs <= n / 2; ++pairs) {
        const std::size_t length = 2 * pairs;
        for (std::size_t left = 0; left <= n - length; ++left) {
            const std::size_t right = left + length - 1;
            Score best = distance(a[left], a[left + 1]);
            if (pairs > 1) {
                const Score* inside = rows.data() + layout.row[left + 1];
                const Score* suffix = columns.data() + layout.column[right] + (left + 2) / 2;
                // Partner left+1: empty inner interval.
                best += suffix[0];
                // Partner right: empty suffix interval.
                Score last = distance(a[left], a[right]);
                last += inside[pairs - 2];
                if (last < best) best = std::move(last);
                // All other partners. Both table reads advance contiguously.
                for (std::size_t k = 1; k + 1 < pairs; ++k) {
                    const std::size_t partner = left + 1 + 2 * k;
                    Score candidate = distance(a[left], a[partner]);
                    candidate += inside[k - 1];
                    candidate += suffix[k];
                    if (candidate < best) best = std::move(candidate);
                }
            }
            rows[layout.row[left] + pairs - 1] = best;
            columns[layout.column[right] + left / 2] = std::move(best);
        }
    }
    if (n % 2 == 0) return rows[n / 2 - 1];
    // The survivor's zero-based index must be even. No pair can straddle it.
    Score best{};
    bool first = true;
    for (std::size_t survivor = 0; survivor < n; survivor += 2) {
        Score candidate{};
        if (survivor > 0) candidate += rows[survivor / 2 - 1];
        if (survivor + 1 < n)
            candidate += rows[layout.row[survivor + 1] + (n - survivor - 1) / 2 - 1];
        if (first || candidate < best) { best = std::move(candidate); first = false; }
    }
    return best;
}

std::string transition_count(std::size_t n) {
    const std::uint64_t m = static_cast<std::uint64_t>(n / 2);
    std::uint64_t factors[3] = {m, m + 1, n % 2 == 0 ? 2*m + 1 : m + 2};
    std::uint64_t divisor = n % 2 == 0 ? 6 : 3;
    for (auto& factor : factors) {
        const std::uint64_t common = std::gcd(factor, divisor);
        factor /= common;
        divisor /= common;
    }
    std::uint64_t result = 1;
    for (const auto factor : factors) {
        if (factor != 0 && result > std::numeric_limits<std::uint64_t>::max() / factor)
            return "null";
        result *= factor;
    }
    return std::to_string(result);
}

void solve_one(std::istream& in, std::ostream& out, bool force_exact, std::size_t case_index) {
    const auto started = std::chrono::steady_clock::now();
    const std::size_t n = size_token(in);
    if (n > std::vector<Integer>().max_size() || n > std::vector<std::int64_t>().max_size())
        throw std::runtime_error("input allocation size is not representable");
    std::vector<Integer> exact;
    std::vector<std::int64_t> fast;
    exact.reserve(n); fast.reserve(n);
    bool fits = !force_exact;
    for (std::size_t i = 0; i < n; ++i) {
        exact.push_back(Integer::decimal(token(in)));
        std::int64_t value = 0;
        if (!exact.back().as_i64(value)) fits = false;
        fast.push_back(value);
    }
    if (fits && n >= 2) {
        const auto extremes = std::minmax_element(fast.begin(), fast.end());
        const std::uint64_t range = distance(*extremes.second, *extremes.first);
        if (range != 0 && n / 2 > std::numeric_limits<std::uint64_t>::max() / range)
            fits = false;
    }
    // At most floor(n/2) differences, each <= range: this checked bound proves
    // that every candidate, intermediate addition, and final uint64 score fits.
    if (fits) out << exact_minimum<std::uint64_t>(fast) << '\n';
    else out << exact_minimum<Natural>(exact) << '\n';
    const double seconds = std::chrono::duration<double>(std::chrono::steady_clock::now()-started).count();
    // Metadata contains dimensions and execution details, never input values.
    std::cerr << "{\"event\":\"case_completed\",\"case_index\":" << case_index
              << ",\"n\":" << n << ",\"seconds\":" << std::setprecision(9) << seconds
              << ",\"dp_transitions\":" << transition_count(n)
              << ",\"arithmetic_path\":\"" << (fits ? "checked_uint64" : "exact_base1e9")
              << "\"}\n";
}

}  // namespace

int main(int argc, char** argv) {
    std::ios::sync_with_stdio(false);
    std::cin.tie(nullptr);
    bool batch = false;
    bool force_exact = false;
    try {
        for (int i = 1; i < argc; ++i) {
            const std::string option(argv[i]);
            if (option == "--batch") batch = true;
            else if (option == "--force-exact") force_exact = true;
            else throw std::runtime_error("unknown option");
        }
        const std::size_t cases = batch ? size_token(std::cin) : 1;
        for (std::size_t i = 0; i < cases; ++i) solve_one(std::cin, std::cout, force_exact, i);
        std::string extra;
        if (std::cin >> extra) throw std::runtime_error("unexpected trailing input");
        return 0;
    } catch (const std::bad_alloc&) {
        std::cerr << "reference failed: allocation limit\n";
    } catch (const std::exception& error) {
        std::cerr << "reference failed: " << error.what() << '\n';
    }
    return 2;
}
