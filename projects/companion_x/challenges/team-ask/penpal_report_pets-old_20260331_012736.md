# PenPal Analysis Report

**Analyst:** ajbarbar
**Generated:** 2026-03-31 01:27:31
**Workspace:** `/workplace/ajbarbar/pets`
**PenPal Version:** 1.3.0b0

> ⚠️ **DISCLAIMER:** PenPal is an experimental AI tool that may miss vulnerabilities, report false positives, or recommend ineffective fixes. It does not replace professional security review. Validate all findings independently. Follow acceptable use policies for projects requiring disclosure.

| Metric | Value |
|--------|-------|
| Assessment Cost | $119.48 |
| Actual Runtime | 07:40:50 |
| GPU Time | 05:43:54 |
| Total Tokens | 20.7M |
| Entrypoints | 82 |
| CWE Checks | 90 |
| Flagged Issues | 45 |
| Dismissed | 19 |
| Plausible | 26 |
| Confirmed Vulnerabilities | 12 |

*The appendix contains per-agent metrics. SQLite database: `~/.penpal/projects.db`*


## Severity Breakdown

<table class="severity-table">
<tr>
<th class="severity-critical">Critical</th>
<th class="severity-high">High</th>
<th class="severity-medium">Medium</th>
<th class="severity-low">Low</th>
<th class="severity-total">Total</th>
</tr>
<tr>
<td class="severity-critical">0</td>
<td class="severity-high">2</td>
<td class="severity-medium">6</td>
<td class="severity-low">1</td>
<td class="severity-total">9</td>
</tr>
</table>


## Security Issues Summary

| ID | Title | Severity | CWE |
|----|-------|----------|-----|
| 16 | Missing Customer Ownership Authorization in VetsController | **High** | CWE-863 |
| 24 | Missing Customer-Level Authorization in addPet Endpoint | **High** | CWE-863 |
| 20 | Missing Marketplace-Level Authorization in Customer Activity Endpoints | **Medium** | CWE-863 |
| 21 | Missing Authorization Check in Pet Profile Save Endpoint | **Medium** | CWE-863 |
| 22 | Missing Authorization on Review Resource Access in RypController | **Medium** | CWE-863 |
| 23 | Missing Authorization Check in getPet Endpoint | **Medium** | CWE-863 |
| 26 | Missing Resource-Level Authorization in listPetsByCustomerIdAndStatus Endpoint | **Medium** | CWE-863 |
| 25 | Missing Authorization in Pet Review Submission Endpoint | **Medium** | CWE-863 |
| 18 | Authentication Bypass in Graffiti Add-to-Cart Endpoint | **Low** | CWE-863 |

## Vulnerability Details

## 1. Missing Customer Ownership Authorization in VetsController

**CWE:** CWE-863 - Missing or Incorrect Authorization  
**Location:** `src/PetsProfileService/src/com/amazon/pets/profileservice/resource/VetsController.java:N/A`  
**Severity:** <span class="severity-text-high">High</span>  

### Impact

Any authenticated calling service can read, create, modify, or delete vet records belonging to arbitrary customers by supplying any `customerId` or `vetId` — the service never verifies that the caller is authorized to act on the specified customer's data. With 100+ active consumers (including `RetailWebsite` shards serving customers globally), a compromised or misconfigured upstream service could enumerate all vet relationships for any customer via `listVetsByCustomerId`, silently overwrite vet records via `updateVet`, or delete vet data via `deleteVet`. This is a classic Insecure Direct Object Reference (IDOR) pattern: the caller supplies the object identifier, and the service trusts it without ownership verification.

The `updateVet` path is the most exposed — it lacks even the marketplace check that `getVet` and `deleteVet` perform, meaning a caller can overwrite any vet record across any marketplace.

### Description

While the `VetsResource` interface carries `@AAA` annotations that enforce service-level authentication (verifying the calling service holds a valid AAA token), no method in `VetsController` or `VetBusinessLogic` verifies that the authenticated caller is authorized to operate on the target customer's data. Every endpoint accepts a caller-supplied `customerId` or `vetId` and trusts it unconditionally.

#### Missing ownership check in `addVet`

The caller supplies a `customerId` embedded inside the `vetIon` payload. The controller deserializes it and passes it straight to the DAO with no verification:

```java
// VetsController.java:61-72
public IonValue addVet(final IonValue vetIon, final String encryptedMarketplaceId) {
    if (!VetConverter.isValidVetIon(vetIon, false)) {
        throw new BadRequestException("vetIon is not valid");
    }
    // ...
    Vet vet = VetConverter.convertFromIonValue(vetIon);       // customerId comes from caller
    vet.setEncryptedMarketplaceId(encryptedMarketplaceId);
    vetBusinessLogic.createVet(vet);                           // saved without ownership check
    return VetConverter.convertToIonValue(vet);
}
```

`VetBusinessLogic.createVet()` (lines 28–53) checks for duplicate vet IDs but never validates that the caller owns the `customerId` embedded in the vet object.

#### Missing ownership check in `listVetsByCustomerId`

The caller supplies an arbitrary `customerId` as a parameter and receives all vet records for that customer:

```java
// VetsController.java:168-176
public IonList listVetsByCustomerId(final String customerId, final String encryptedMarketplaceId) {
    if (StringUtils.isEmpty(customerId)) {
        throw new BadRequestException("customerId should not be empty or null");
    }
    // No check: does the caller own this customerId?
    List<Vet> vets = vetBusinessLogic.listVetsByCustomerId(customerId, encryptedMarketplaceId);
    // ...
}
```

#### Missing ownership check in `updateVet` — also missing marketplace check

`updateVet` is the most permissive endpoint. It validates input format and that the `vetId` matches, but performs no marketplace check (unlike `getVet` at line 126 and `deleteVet` at line 62 of `VetBusinessLogic`) and no customer ownership check:

```java
// VetsController.java:86-101
public IonValue updateVet(final String vetId, final IonValue vetIon, final String encryptedMarketplaceId) {
    // ...
    Vet vet = VetConverter.convertFromIonValue(vetIon);
    if (!vetId.equals(vet.getVetId())) {
        throw new BadRequestException("vetId does not match vetIon");
    }
    vet.setEncryptedMarketplaceId(encryptedMarketplaceId);
    vetBusinessLogic.updateVet(vet);  // No marketplace or customer check
    return VetConverter.convertToIonValue(vet);
}
```

And in `VetBusinessLogic.updateVet()` (lines 116–135), the existing vet is looked up only to confirm it exists, then the caller-supplied object is saved directly — the existing vet's `customerId` is never compared to the caller's identity:

```java
// VetBusinessLogic.java:116-130
public void updateVet(final Vet requestVet) {
    String vetId = requestVet.getVetId();
    Vet existingVet = vetDAO.lookupVetById(vetId);
    if (existingVet != null) {
        vetDAO.saveVet(requestVet);   // Overwrites without checking ownership
    } else {
        throw new IllegalArgumentException("Cannot find vet with vetId " + vetId);
    }
}
```

#### Contrast with `PetBusinessLogic` — the correct pattern already exists

`PetBusinessLogic.deactivatePet()` demonstrates the expected authorization check at line 282:

```java
// PetBusinessLogic.java:277-284
public Pet deactivatePet(final String petId, final String customerId, String encryptedMarketplaceId) {
    Pet existingPet = petDAO.lookupPetById(petId);
    if (null != existingPet) {
        if (!customerId.equals(existingPet.getCustomerId())) {
            throw new NotAuthorizedException(NOT_AUTHORIZED_RESPONSE);
        }
        // ...
    }
}
```

This pattern — comparing the caller-asserted `customerId` against the stored record's `customerId` — is completely absent from every `VetBusinessLogic` method.

### Recommendation

Add customer ownership verification to every mutating and read operation in `VetBusinessLogic`, following the pattern already established in `PetBusinessLogic.deactivatePet()`. The caller's `customerId` should be passed through from the controller and compared against the stored record's `customerId` before any data is returned or modified.

For operations that look up by `vetId` (`getVet`, `updateVet`, `deleteVet`), accept a `customerId` parameter from the controller and verify it matches the stored vet record:

```java
// VetBusinessLogic.java — updateVet with ownership check
public void updateVet(final Vet requestVet, final String callerCustomerId) {
    String vetId = requestVet.getVetId();
    Vet existingVet = vetDAO.lookupVetById(vetId);
    if (existingVet == null) {
        throw new IllegalArgumentException("Cannot find vet with vetId " + vetId);
    }
    if (!callerCustomerId.equals(existingVet.getCustomerId())) {
        throw new NotAuthorizedException("Not authorized to modify this vet record");
    }
    vetDAO.saveVet(requestVet);
}
```

Apply the same check to `deleteVet` and `getVet`. For `createVet`, validate that the `customerId` embedded in the vet payload matches the caller's asserted identity. For `listVetsByCustomerId`, ensure the caller can only query their own `customerId`.

Additionally, `updateVet` in `VetsController` should add the marketplace consistency check (`encryptedMarketplaceId.equals(existingVet.getEncryptedMarketplaceId())`) that `getVet` and `deleteVet` already enforce, to prevent cross-marketplace record manipulation.


---

## 2. Missing Customer-Level Authorization in addPet Endpoint

**CWE:** CWE-863 - Missing or Incorrect Authorization  
**Location:** `src/PetsProfileService/src/com/amazon/pets/profileservice/resource/PetsController.java:122`  
**Severity:** <span class="severity-text-high">High</span>  

### Impact

An authenticated upstream service caller can supply an arbitrary `customerId` in the `addPet` request body to manipulate pet records across customer accounts. This was externally reported via Amazon's Bug Bounty program (HackerOne #3586880) and confirmed exploitable from `amazon.com/yourpets/add`: an attacker intercepts the pet creation POST request, replaces `petId` with a victim's existing pet ID, and the server reassigns that pet record to the attacker's account — effectively deleting it from the victim's profile. The attack requires only a standard authenticated session and a known or guessed `petId`.

A partial fix (CR-259676545) now blocks the takeover-of-existing-pets vector by checking customer ownership when a `petId` already exists in the database. However, the normal creation flow — where `petId` is empty or new — still persists whatever `customerId` the caller supplies without any validation, allowing pet records to be created under arbitrary customer accounts. With 150+ AAA clients including `AmazonAPI` and 130+ `RetailWebsite*` instances, any upstream service that forwards user-controlled request bodies without independently validating the embedded `customerId` would expose this gap.

### Description

The `addPet` implementation at line 122 extracts `customerId` directly from the caller-supplied `IonValue` request body and passes it to the business logic layer without verifying that the caller is authorized to act on behalf of that customer.

```java
// PetsController.java:122
Pet pet = PetConverter.convertFromIonValue(petIon);
log.info("Adding new pet for customerId {} in marketplace {}", pet.getCustomerId(), encryptedMarketplaceId);
result = petBusinessLogic.createPet(encryptedMarketplaceId, pet, tags);
```

The `customerId` stored in the created `Pet` object is entirely attacker-controlled — whatever value is embedded in `petIon` is what gets persisted. Neither `petBusinessLogic.createPet()` nor the DAO layer perform any authorization check on this value for new pet creation.

#### Delegation Chain

All three `addPet` overloads form a single delegation chain terminating at the same unprotected code:

- `addPet(IonValue, String)` (line 64) → `addPet(String, IonValue, String, List)` (line 71) → `addPet(String, IonValue, String, List, String, String)` (line 122)

Each overload is annotated with `@AAA(serviceName=…, operationName="addPet")`, but this annotation only gates **which service** is allowed to call the operation. It does not bind the authenticated session's customer identity to the `customerId` in the request body.

#### Partial Fix on Mainline

CR-259676545 added a customer ownership check in `PetBusinessLogic.createPet()`, but only for the branch where a `petId` already exists in the database:

```java
// PetBusinessLogic.java:87-94 (mainline)
if (isNotEmpty(petId)) {
    Pet existingPet = petDAO.lookupPetById(petId);
    if (null != existingPet) {
        if (!Objects.equals(existingPet.getCustomerId(), pet.getCustomerId())) {
            throw new ForbiddenException("RequestedCustomerId and CustomerId associated with this petId are mismatched");
        }
        // ...
    }
}
// Falls through to petDAO.savePet(pet, tags, true) with unchecked customerId
```

When `petId` is empty or does not match an existing record (the normal new-pet creation flow at line 118), the caller-supplied `customerId` is persisted with no validation.

#### Secure Pattern Already Exists in Codebase

The newer AAPI endpoint `createPetProfileAAPI` demonstrates the correct pattern: it extracts `customerId` from authenticated API headers via `getCustomerId(apiHeaders, metrics)` and passes it to `PetConverter.convertFromCreatePetProfileRequest(createPetProfileRequest, customerId, ...)` — the customer identity is server-derived, never caller-supplied. Similarly, `deactivatePet()` explicitly checks `customerId.equals(existingPet.getCustomerId())` and throws `NotAuthorizedException`. The legacy Ion-based `addPet` endpoint was never retrofitted with either pattern.

### Recommendation

Add a customer-level authorization check in the main `addPet` method at line 122, before calling `petBusinessLogic.createPet()`. The authenticated customer identity must be resolved from the request context (following the AAPI pattern) and compared against the `customerId` extracted from the `IonValue` body:

```java
// PetsController.java — inside addPet at line 122, after PetConverter.convertFromIonValue
Pet pet = PetConverter.convertFromIonValue(petIon);

String authenticatedCustomerId = /* resolve from request/auth context, matching getCustomerId(apiHeaders, metrics) pattern */;
if (!authenticatedCustomerId.equals(pet.getCustomerId())) {
    throw new NotAuthorizedException(NOT_AUTHORIZED_RESPONSE);
}

result = petBusinessLogic.createPet(encryptedMarketplaceId, pet, tags);
```

Because both deprecated overloads delegate into this method, a single check here fixes all three entry points. Consider moving this check into `PetBusinessLogic.createPet()` alongside the existing `deactivatePet` and the CR-259676545 ownership checks to keep authorization logic consistently in the business layer.


---

## 3. Missing Marketplace-Level Authorization in Customer Activity Endpoints

**CWE:** CWE-863 - Missing or Incorrect Authorization  
**Location:** `src/PetsProfileService/src/com/amazon/pets/profileservice/resource/ActivitiesController.java:36`  
**Severity:** <span class="severity-text-medium">Medium</span>  

### Impact

An authenticated service-to-service caller authorized for one marketplace (e.g., US — `ATVPDKIKX0DER`) can request customer signup and dropout lists for any other marketplace (e.g., DE — `A1PA6795UKMFR9`) and receive the full, unscoped result set. Because the `encryptedMarketplaceId` path parameter is accepted but silently discarded, the underlying DynamoDB query returns customer IDs from all marketplaces globally, regardless of which marketplace the caller specified or is authorized to access.

ServiceLens shows over 150 active `RetailWebsite` client instances across global cells (US, EU, JP, and others), plus additional callers such as `AmazonAPI`, `DigitalVideoWebsite`, and `PetsPrescriptionService`. Any of these callers — or an attacker who compromises one — can enumerate customer identifiers across marketplace boundaries. Leaking EU customer identifiers to a US-serving caller (or vice versa) creates regulatory exposure under GDPR and similar privacy frameworks. The `@AAA` annotation on the interface authorizes the *operation* but performs no check on *which marketplace* the caller may access, so the only barrier is having an active AAA relationship to PetsProfileService, which 150+ services already hold.

### Description

#### Discarded Marketplace Parameter

The `getCustomerSignUpList` method at line 36 accepts `encryptedMarketplaceId` as a parameter but never passes it to any downstream method:

```java
// ActivitiesController.java:36-44
@Override
public IonList getCustomerSignUpList(final int duration, final String start, final String end,
        final String encryptedMarketplaceId) {
    if (duration > 0 && StringUtils.isNotBlank(start) && StringUtils.isNotBlank(end)) {
        throw new BadRequestException("Query by valid hour duration or start/end date.");
    }

    DateTime[] dates = duration > 0 ? parseDateTime(DateTime.now(), duration) : parseDateTime(start, end);
    return getCustomerListBetween(dates[0], dates[1]); // encryptedMarketplaceId is silently dropped
}
```

`getCustomerListBetween` delegates to `customersBusinessLogic.getCompletedProfilesCustomers(start, end)`, which calls `petDAO.queryCustomersCompletedBetween(start, end)`. None of these methods accept or apply a marketplace filter.

#### Unscoped DynamoDB Query

The final query in `PetDAOImpl` (lines 306–321) filters only by `Status` (hash key) and `CompletionDate` (range key):

```java
// PetDAOImpl.java:309-317
DynamoDBQueryExpression<PetModel> queryExpression =
    new DynamoDBQueryExpression<PetModel>()
        .withHashKeyValues(model)                                    // Status only
        .withRangeKeyCondition("CompletionDate", completionDateCondition) // Date range only
        .withConsistentRead(false);
```

The `PetModel` has an `EncryptedMarketplaceID` attribute (line 40–41 of `PetModel.java`), but it is never set as a filter condition. This means the query returns customers across every marketplace in the table.

#### Identical Issue in Dropout Endpoint

`getCustomerDropoutList` (line 46–55) follows the same pattern — accepts `encryptedMarketplaceId` and discards it before calling `getCustomerDropoutListBetween(dates[0], dates[1])`.

#### Exploitation Path

A service with an active AAA relationship (e.g., a RetailWebsite cell serving the US marketplace) sends:

```
GET /marketplaces/A1PA6795UKMFR9/activities/signup?duration=24
```

The `MarketplaceIdValidationFilter` validates that `A1PA6795UKMFR9` is in the approved marketplace list but does not verify the caller is authorized for *that specific* marketplace. The `@AAA` annotation on the `ActivitiesResource` interface authorizes the operation generically. The response contains customer IDs from all marketplaces — not just the German marketplace the caller requested.

### Recommendation

Pass `encryptedMarketplaceId` through the entire call chain and add it as a query filter condition in the DynamoDB query. In `getCustomerListBetween` (and the equivalent dropout method), propagate the marketplace ID down to `PetDAOImpl.queryCustomersCompletedBetween`:

```java
// ActivitiesController.java – pass marketplace through
return getCustomerListBetween(dates[0], dates[1], encryptedMarketplaceId);

// PetDAOImpl.java – add filter expression to scope results
DynamoDBQueryExpression<PetModel> queryExpression =
    new DynamoDBQueryExpression<PetModel>()
        .withHashKeyValues(model)
        .withRangeKeyCondition("CompletionDate", completionDateCondition)
        .withFilterExpression("EncryptedMarketplaceID = :mktId")
        .withExpressionAttributeValues(
            Collections.singletonMap(":mktId", new AttributeValue().withS(encryptedMarketplaceId)))
        .withConsistentRead(false);
```

Apply the same fix to both `getCustomerSignUpList` and `getCustomerDropoutList` code paths. After deploying the fix, verify with integration tests that a request for marketplace A returns zero results belonging to marketplace B. As a follow-up hardening step, consider adding caller-level marketplace authorization in the AAA policy so that each service is only permitted to query the marketplaces it legitimately serves.


---

## 4. Missing Authorization Check in Pet Profile Save Endpoint

**CWE:** CWE-863 - Missing or Incorrect Authorization  
**Location:** `src/PetsProfileWebsite/src/com/amazon/pets/profile/website/controller/core/GraffitiController.java:295`  
**Severity:** <span class="severity-text-medium">Medium</span>  

### Impact

An authenticated customer who is not eligible for the Graffiti feature—either because they already have a pet profile or have explicitly dismissed the Graffiti widget—can bypass the eligibility check and create a Graffiti-tagged pet profile for their own account by calling the save endpoint directly. The impact is bounded: the customer ID is derived from the server-side session (`CustomerId.resolveCurrent()`), so an attacker cannot create profiles for other users, and a functionally equivalent pet creation capability already exists via the normal `/yourpets/add` endpoint. The practical consequences are pollution of Graffiti A/B experiment analytics with ineligible users, generation of Graffiti-tagged product recommendations outside the intended flow, and circumvention of the one-profile-per-customer business rule enforced by the feature eligibility logic.

### Description

The `savePetProfile` handler at line 295 accepts a POST to `/yourpets/save-pet-profile-graffiti` and creates a new pet profile without verifying whether the caller is an eligible "target customer." The companion display method `renderGraffitiWidget` correctly gates on `isTargetCustomer()`, but the save action does not.

#### Authorization enforced in display logic

`renderGraffitiWidget` (lines 195–206) checks eligibility before rendering the Graffiti UI:

```java
// GraffitiController.java:195-206
Try<Boolean> tryGetIsTargetCustomer = Try
    .of(() -> isTargetCustomer(widgetArgs.get(MARKETPLACE_ID), widgetArgs.get(CUSTOMER_ID)))
    .recover(Exception.class, (ex) -> {
        log.error("Failed to resolve target customer info", ex);
        return false;
    });
boolean isTargetCustomer = tryGetIsTargetCustomer.getOrElse(false);
if (!isTargetCustomer || deviceType == null) {
    response.setStatus(HttpStatus.SC_NO_CONTENT); // 204 — widget not shown
    return null;
}
```

`isTargetCustomer()` (lines 525–533) returns `true` only when the customer has **not** opted out **and** has **no** existing pet profiles:

```java
// GraffitiController.java:525-533
private Boolean isTargetCustomer(final String marketplaceId, final String customerId) {
    String marketplace = Optional.ofNullable(marketplaceId).orElseGet(this::resolveMarketplaceId);
    String customer = Optional.ofNullable(customerId).orElseGet(this::getCustomerId);
    return !petsProfileService.getIsPetProfileGraffitiOptOut(customer, marketplace)
            && CollectionUtils.isEmpty(petsProfileService.listPetsByCustomerId(customer, marketplace));
}
```

#### Authorization missing in save logic

`savePetProfile` (line 295) proceeds directly to pet creation with no call to `isTargetCustomer()`:

```java
// GraffitiController.java:295+ (simplified)
public AjaxJSONResponse<GraffitiRecommendations> savePetProfile(
        final HttpServletRequest request,
        final @RequestParam(name = "ref_") Optional<String> refTag,
        final @RequestBody GraffitiPetInfo graffitiPetInfo) {

    String marketplaceId = resolveMarketplaceId();
    String customerId = getCustomerId(); // session-bound, not attacker-controlled

    // ⚠️ No isTargetCustomer() check

    final String browseNodeForRecs = getValidatedBrowseNode(graffitiPetInfo.getBrowseNode());
    Pet pet = newPet(graffitiPetInfo, marketplaceId, customerId);
    pet.setClientServiceTags("Graffiti");
    savedPet = petsProfileService.addNewPet(marketplaceId, pet, "",
            ImmutableList.of(pet.getClientServiceTags()));
    // ... returns recommendations
}
```

#### Exploitation flow

The `@RequiresHttps` and `@RequiresValidToken` annotations ensure the caller is an authenticated customer over HTTPS with a valid CSRF token, but these controls do not enforce Graffiti eligibility. An ineligible user can:

1. Visit any HTTPS page to obtain a valid CSRF token from the session.
2. POST directly to `/yourpets/save-pet-profile-graffiti` with a `GraffitiPetInfo` JSON body (e.g., `{"petCategory":"DOG","breed1":"Labrador","browseNode":"..."}`).
3. The endpoint creates the pet profile and returns product recommendations, bypassing the target-customer gate entirely.

The downstream `PetsProfileService.addNewPet` performs format validation only and contains no Graffiti eligibility check.

### Recommendation

Add the `isTargetCustomer()` guard at the beginning of `savePetProfile`, returning an error response when the caller is not eligible:

```java
// GraffitiController.java — inside savePetProfile, after resolving customerId
if (!isTargetCustomer(marketplaceId, customerId)) {
    log.info("Rejected Graffiti save for ineligible customerId: {}", customerId);
    response.setSuccess(false);
    return response;
}
```

Place this check immediately before the `getValidatedBrowseNode` call at line ~315, mirroring the pattern already used in `renderGraffitiWidget`. Wrap the call in a `Try` with a `recover` block that defaults to `false` on failure, consistent with the existing defensive pattern in the display path.


---

## 5. Missing Authorization on Review Resource Access in RypController

**CWE:** CWE-863 - Missing or Incorrect Authorization  
**Location:** `src/PetsProfileWebsite/src/com/amazon/pets/profile/website/controller/core/RypController.java:114`  
**Severity:** <span class="severity-text-medium">Medium</span>  

### Impact

An authenticated user can retrieve another user's private pet profile data—including pet name, breed, birthday, photo URL, and pet type—by supplying a crafted `petsReviewId` targeting a known victim customer ID. The attack is bounded by the requirement that the attacker must be authenticated and must know or guess the victim's customer ID and a valid ASIN they reviewed, but the `reviewId` format (`marketplaceId_asin_customerId`) is deterministic and easily constructed. The leaked data is limited to pet profiles tagged in product reviews; it does not expose financial information, account credentials, or allow modification of victim data.

### Description

The `GET /yourpets/ryp` endpoint requires authentication (`@RequiresAuthenticatedUser`) but never verifies that the authenticated user owns the review being requested. A user-supplied `petsReviewId` parameter flows through every layer—controller, service, business logic, and DAO—without a single ownership check.

#### Unvalidated Review ID Accepted at Controller

At line 126, the controller reads `petsReviewId` directly from the request and passes it to the backend:

```java
// RypController.java:124-136
String asin = request.getParameter("asin");                              // L124
boolean isEdit = Boolean.parseBoolean(request.getParameter("isEdit"));   // L125
String reviewId = request.getParameter("petsReviewId");                  // L126 — user-controlled
String customerId = getCustomerId();                                      // L128 — from session (safe)

if (isEdit && reviewId == null) {
    reviewId = constructReviewId(marketplaceId, asin, customerId);        // L133 — only used when reviewId is null
}

RypProductReview productReview = petsProfileService.getReviewData(asin, marketplaceId, customerId, reviewId); // L135
```

When `isEdit` is `false` or a `petsReviewId` is already supplied, the user-controlled value is used as-is. After the call returns, the controller renders `productReview.getTaggedPets()` and `productReview.getOtherPetType()` into the view **without checking whether the review belongs to the authenticated `customerId`**.

#### No Ownership Check in Business Logic

The service layer (`PetsProfileServiceImpl.java:410-419`) passes all parameters unchanged. The business logic fetches the review by `reviewId` alone and never compares the review's owner to the authenticated caller:

```java
// PetBusinessLogic.java:365-420
public PetProductReview getReviewData(PetProductReview petProductReview) {
    String customerId = petProductReview.getCustomerId(); // authenticated user
    // allActivePets correctly scoped to authenticated user
    petProductReviewResult.setAllActivePets(listActivePetsByCustomerIdWithImage(customerId, ...));

    if (isNotEmpty(reviewId)) {
        List<PetReviewModel> reviewModel = petReviewDAO.getPetReview(reviewId); // NO ownership check
        petProductReviewResult.setOtherPetType(reviewModel.get(0).getOtherPetType());
        petProductReviewResult.setTaggedPets(reviewModel.stream()
            .map(petReview -> getPet(petReview.getPetId(), true, ...)) // returns victim's pet data
            ...);
    }
}
```

#### DAO Queries by Review ID Only

The DynamoDB query uses only the `externalReviewId` hash key—no customer-scoped filter is applied:

```java
// PetReviewDAO.java
new DynamoDBQueryExpression<PetReviewModel>()
    .withHashKeyValues(PetReviewModel.builder().externalReviewId(reviewId).build())
```

#### Attack Flow

The `reviewId` format is deterministic (`constructReviewId` concatenates `marketplaceId + "_" + asin + "_" + customerId`). An attacker authenticated as Customer A sends:

```
GET /yourpets/ryp?asin=B08XYZ&isEdit=false&petsReviewId=ATVPDKIKX0DER_B08XYZ_VICTIM_CUSTOMER_ID
```

The response renders the victim's tagged pet profiles (name, breed, birthday, photo URL) inside the attacker's browser. The `allActivePets` field remains scoped to the attacker's own pets, but the `taggedPets` and `otherPetType` fields leak the victim's data.

#### Contrast with POST Endpoint

The POST handler (`rypRemoteWidgetPost`, line 218) correctly always binds `customerId` from the session when building `RypProductReview`, making this GET endpoint an inconsistency rather than an application-wide pattern.

### Recommendation

Add an ownership check in `PetBusinessLogic.getReviewData()` immediately after fetching the review, so the fix protects all callers—not just this controller:

```java
// PetBusinessLogic.java — inside getReviewData(), after fetching reviewModel
if (isNotEmpty(reviewId)) {
    List<PetReviewModel> reviewModel = petReviewDAO.getPetReview(reviewId);
    if (reviewModel.isEmpty()) {
        throw new ResourceNotFoundException("Review not found");
    }

    // Verify the authenticated user owns this review
    String reviewCustomerId = reviewModel.get(0).getCustomerId();
    if (!customerId.equals(reviewCustomerId)) {
        throw new AuthorizationException("Authenticated user does not own the requested review");
    }

    petProductReviewResult.setOtherPetType(reviewModel.get(0).getOtherPetType());
    // ... rest of tagged pets logic
}
```

As a hardening measure, also add a redundant check in `RypController.getRypRemoteWidget()` after line 135 to compare `productReview.getCustomerId()` against the authenticated `customerId`, following defense-in-depth principles.


---

## 6. Missing Authorization Check in getPet Endpoint

**CWE:** CWE-863 - Missing or Incorrect Authorization  
**Location:** `src/PetsProfileService/src/com/amazon/pets/profileservice/resource/PetsController.java:213`  
**Severity:** <span class="severity-text-medium">Medium</span>  

### Impact

Exploitation requires authenticated service-to-service credentials (AAA/CloudAuth), meaning only one of the 150+ registered consumer services can reach this endpoint — not arbitrary internet attackers. However, any of those authenticated consumers can retrieve any pet profile in the system by supplying an arbitrary `petId`, regardless of whether that pet belongs to the caller's marketplace or to a customer the caller is authorized to serve. This means a single compromised, misconfigured, or internally-malicious consumer service can enumerate pet IDs and exfiltrate pet profile data (customer IDs, pet names, health details) across all marketplace and customer boundaries. Because the `encryptedMarketplaceId` parameter is never validated against the retrieved pet's actual marketplace, cross-marketplace data leakage is possible — a US-scoped service could retrieve EU pet profiles, potentially violating GDPR data localization requirements. The pet profile data is classified as Confidential (not Restricted), which bounds the severity, but the 150+ consumer blast radius means a single compromise cascades to the entire pet profile dataset.

### Description

The `getPet` endpoint at line 213 of `PetsController.java` retrieves a pet profile by `petId` without verifying that the caller is authorized to access that specific pet. The method accepts both `petId` and `encryptedMarketplaceId` from the caller but uses only `petId` for the lookup and never validates the result against the marketplace parameter or any customer ownership.

#### The Vulnerable Code Path

At line 213, the controller delegates directly to `petBusinessLogic.getPet()` and returns the result without any authorization check:

```java
// PetsController.java:213-241
@Override
public IonValue getPet(final String petId, final String encryptedMarketplaceId) {
    ServiceMetrics metrics = new ServiceMetrics(servletRequest, "GetPet");

    if (StringUtils.isEmpty(petId)) {
        metrics.count(FAILURE);
        throw new BadRequestException("petId should not be empty or null");
    }

    try {
        log.info("look up pet {} in marketplace {}", petId, encryptedMarketplaceId);
        Pet pet = petBusinessLogic.getPet(petId, true, encryptedMarketplaceId);
        if (null != pet) {
            IonValue result = PetConverter.convertToIonValue(pet);
            metrics.count(SUCCESS);
            return result;  // ← Returned without ownership or marketplace check
        } else {
            throw new NotFoundException("unable to find pet with petId: " + petId);
        }
    }
    // ...
}
```

In `PetBusinessLogic.getPet()` (line 222), the lookup queries DynamoDB by `petId` alone. The `encryptedMarketplaceId` is only used to backfill a null field — it is never used as a filter or validation constraint:

```java
// PetBusinessLogic.java:222-232
public Pet getPet(final String petId, final boolean needImageUrlUpdate, final String encryptedMarketplaceId) {
    Pet pet = petDAO.lookupPetById(petId);  // ← Fetches any pet by ID, no marketplace filter
    if (pet != null) {
        assignMarketplaceIdToPetIfMissing(pet, encryptedMarketplaceId);  // ← Only assigns if null, never validates
    }
    // ...
    return pet;
}
```

The DAO confirms the query uses only the hash key with no marketplace filtering:

```java
// PetDAOImpl.java:143-156
public Pet lookupPetById(final String petId) {
    PetModel model = new PetModel();
    model.setPetId(petId);
    DynamoDBQueryExpression<PetModel> queryExpression =
            new DynamoDBQueryExpression<PetModel>().withHashKeyValues(model)
                    .withConsistentRead(true);
    // ...
}
```

Compare this with `lookupActivePetsByCustomerId` (line 182), which correctly scopes queries with `dynamoQueryExpressionForPetsInMarketplaceWithStatus(customerId, encryptedMarketplaceId, ...)`.

#### The Authorization Pattern That Was Omitted

The codebase already has the correct authorization pattern in `deactivatePet` (line 277), which validates customer ownership before acting:

```java
// PetBusinessLogic.java:277-283
public Pet deactivatePet(final String petId, final String customerId, String encryptedMarketplaceId) {
    Pet existingPet = petDAO.lookupPetById(petId);
    if (null != existingPet) {
        if (!customerId.equals(existingPet.getCustomerId())) {
            throw new NotAuthorizedException(NOT_AUTHORIZED_RESPONSE);  // ← Correct pattern
        }
        // ...
    }
}
```

The `getPet` endpoint neither accepts a `customerId` to validate ownership, nor checks that the retrieved pet's `encryptedMarketplaceId` matches the caller-supplied marketplace. Both checks are absent.

### Recommendation

Add marketplace boundary validation in `PetBusinessLogic.getPet()` to reject requests where the retrieved pet does not belong to the caller's marketplace. This is the most targeted fix since `getPet` is a service-to-service endpoint that does not receive a `customerId`:

```java
// PetBusinessLogic.java - updated getPet method
public Pet getPet(final String petId, final boolean needImageUrlUpdate, final String encryptedMarketplaceId) {
    log.debug("looking up pet {}", petId);
    Pet pet = petDAO.lookupPetById(petId);
    if (pet != null) {
        // Enforce marketplace boundary: reject if pet belongs to a different marketplace
        if (pet.getEncryptedMarketplaceId() != null
                && !pet.getEncryptedMarketplaceId().equals(encryptedMarketplaceId)) {
            log.warn("Marketplace mismatch for pet {}. Requested: {}, Actual: {}",
                    petId, encryptedMarketplaceId, pet.getEncryptedMarketplaceId());
            return null; // Treat as not found to avoid leaking existence
        }
        assignMarketplaceIdToPetIfMissing(pet, encryptedMarketplaceId);
    }
    if (needImageUrlUpdate) {
        handleImageUrlUpdate(pet, encryptedMarketplaceId);
    }
    return pet;
}
```

For longer-term hardening, consider extending the `getPet` REST contract to accept a `customerId` parameter and validating ownership with the same `customerId.equals(existingPet.getCustomerId())` pattern used in `deactivatePet`. This would provide defense-in-depth against cross-customer access within the same marketplace.


---

## 7. Missing Resource-Level Authorization in listPetsByCustomerIdAndStatus Endpoint

**CWE:** CWE-863 - Missing or Incorrect Authorization  
**Location:** `src/PetsProfileService/src/com/amazon/pets/profileservice/resource/PetsController.java:318`  
**Severity:** <span class="severity-text-medium">Medium</span>  

### Impact

Any authenticated service that can reach PetsProfileService can retrieve any customer's pet profile data (names, species, breeds, images, health status, memorial status) by supplying an arbitrary `customerId` value. ServiceLens shows 150+ active dependents including `AmazonAPI`, `AlexaCategoryReorderService`, `PetsRxHorizonteService`, and numerous `RetailWebsite*` instances — so a single compromised or misconfigured calling service could enumerate pet profiles across the entire customer base by iterating customer IDs. The blast radius is bounded by the fact that the caller must hold valid CloudAuth credentials for PetsProfileService, but within that trust boundary no further restriction exists on which customer records can be read.

### Description

The `listPetsByCustomerIdAndStatus` method at line 318 accepts a caller-supplied `customerId` and returns that customer's pet records without verifying the caller is authorized to access them.

#### Missing Authorization in the Request Path

The endpoint performs input validation via `checkInputValues()` (lines 304–315), which only confirms the parameters are non-empty and the status is a valid enum value. After validation, the method proceeds directly to data retrieval with no authorization gate:

```java
// PetsController.java:318-330
@Override
public IonList listPetsByCustomerIdAndStatus(final String customerId, final String statusStr,
                                              final String encryptedMarketplaceId) {
    ServiceMetrics metrics = new ServiceMetrics(servletRequest, "ListPetsByCustomerIdAndStatus");

    String errorMsg = checkInputValues(customerId, statusStr);   // input validation only
    if (errorMsg != null) {
        metrics.count(FAILURE);
        throw new BadRequestException(errorMsg);
    }

    // No authorization check — directly fetches data for the supplied customerId
    PetProfileStatus status = PetProfileStatus.valueOf(statusStr.toUpperCase(Locale.ROOT));
    List<Pet> pets = petBusinessLogic.listPetsByCustomerIdAndStatusWithImage(
            customerId, status, encryptedMarketplaceId);
    // ...
}
```

The business logic layer (`PetBusinessLogic.listPetsByCustomerIdAndStatusWithImage`, line 340) also performs no authorization — it passes the `customerId` straight through to `petDAO.lookupPetsByCustomerIdAndStatus()`.

#### Framework Auth Does Not Cover This Gap

`AuthConfig.java` configures CloudAuth (service identity) and AAA (annotation-gated operation authorization), but the `@AAA` annotation is only applied to `RemoteStrategyController` methods — not to `PetsController`. This means CloudAuth authenticates the *calling service*, but nothing validates that the calling service is entitled to query a *specific customer's* data.

Neither JAX-RS filter (`MarketplaceIdValidationFilter`, `ARestMetricsFilter`) performs customer-level authorization either.

#### Contrast with Correct Pattern in the Same Codebase

The `deactivatePet` method in `PetBusinessLogic` (line 277) demonstrates the expected authorization check:

```java
// PetBusinessLogic.java:277-284
public Pet deactivatePet(final String petId, final String customerId, String encryptedMarketplaceId) {
    Pet existingPet = petDAO.lookupPetById(petId);
    if (null != existingPet) {
        if (!customerId.equals(existingPet.getCustomerId())) {
            throw new NotAuthorizedException(NOT_AUTHORIZED_RESPONSE);   // ← resource-level authz
        }
        // ...
    }
}
```

This pattern verifies the caller-supplied `customerId` matches the resource owner before proceeding. The `listPetsByCustomerIdAndStatus` endpoint lacks an equivalent check.

### Recommendation

Add resource-level authorization that binds the caller's identity to the requested `customerId`. The most appropriate approach depends on the caller type:

For service-to-service calls, require the calling service to pass an authenticated customer identity (e.g., a signed customer token or a claim from a prior authentication step) and validate it matches the `customerId` parameter before querying data. At minimum, add an `@AAA` annotation to the method in `PetsController` to restrict which service operations can invoke this endpoint, consistent with the pattern already used in `RemoteStrategyController`:

```java
@AAA(serviceName = "PetsProfileService", operationName = "listPetsByCustomerIdAndStatus")
@Override
public IonList listPetsByCustomerIdAndStatus(final String customerId, final String statusStr,
                                              final String encryptedMarketplaceId) {
    // Validate that the authenticated caller context is authorized for this customerId
    String authenticatedCustomerId = resolveAuthenticatedCustomerId(servletRequest);
    if (!customerId.equals(authenticatedCustomerId)) {
        throw new NotAuthorizedException(Response.status(401).build());
    }
    // ... existing logic
}
```

Additionally, apply the same authorization pattern to other read endpoints in `PetsController` that accept a caller-supplied `customerId` (e.g., `listActivePetsByCustomerId`) to prevent the same class of vulnerability elsewhere in the controller.


---

## 8. Missing Authorization in Pet Review Submission Endpoint

**CWE:** CWE-863 - Missing or Incorrect Authorization  
**Location:** `src/PetsProfileService/src/com/amazon/pets/profileservice/resource/PetsController.java:105`  
**Severity:** <span class="severity-text-medium">Medium</span>  

### Impact

A compromised or misconfigured internal service—any of the 160+ services authorized to call this endpoint—can submit pet reviews under an arbitrary `customerId`, associating pets from one customer's profile with a review attributed to a completely different customer. This allows cross-customer data manipulation (corrupting review-based pet profile data and spoofing pet-tag associations) but is bounded by the requirement that the attacker must already hold valid service-to-service credentials (AAA authentication), meaning external or anonymous attackers cannot directly reach the endpoint. The integrity impact is limited to pet review and pet-tagging data within PetsProfileService; no confidential data is leaked and no availability impact exists.

The high number of authorized callers (160+ services including RetailWebsite instances, AmazonAPI, DigitalVideoWebsite, and others) makes it statistically unlikely that every caller correctly binds `customerId` to an authenticated user identity, and a single compromised caller provides a direct path to write review data on behalf of any customer.

### Description

The `submitPetReview` endpoint accepts a `customerId` from the request body and uses it to create review records without verifying that the caller is authorized to act on behalf of that customer.

#### Unvalidated Customer Identity

At `PetsController.java:105`, the endpoint passes the caller-supplied review data directly to business logic with no authorization gate:

```java
// PetsController.java:105-107
@Override
public String submitPetReview(String encryptedMarketplaceId, PetProductReview reviewData) {
    return petBusinessLogic.submitReviewData(reviewData);
}
```

The `encryptedMarketplaceId` path parameter is ignored for authorization purposes. Inside `PetBusinessLogic.submitReviewData` (line 416–439), tagged pets are looked up by ID but never checked for ownership:

```java
// PetBusinessLogic.java (submitReviewData)
Pet existingPet = petDAO.lookupPetById(pet.getPetId());
// MISSING: ownership check — existingPet.getCustomerId() is never compared to reviewData.getCustomerId()
return getSavedPet(getUpdatedPet(pet, existingPet));
```

The DAO layer then constructs the database key directly from the untrusted `customerId`:

```java
// PetReviewDAO.java:50-55
String reviewId = StringUtils.join(ImmutableList.of(
    petProductReview.getMarketplaceId(),
    petProductReview.getAsin(),
    petProductReview.getCustomerId()), SEPARATOR);  // caller-controlled
```

#### Contrast with Existing Authorization Patterns

The same class correctly validates customer ownership in `deactivatePet`:

```java
// PetBusinessLogic.java (deactivatePet)
if (!customerId.equals(existingPet.getCustomerId())) {
    throw new NotAuthorizedException(NOT_AUTHORIZED_RESPONSE);
}
```

This confirms the authorization check in `submitReviewData` is a gap, not an architectural choice.

#### Exploitation Flow

1. An authorized internal service calls `submitPetReview` with a crafted `PetProductReview` containing a victim's `customerId` and attacker-chosen pet IDs.
2. The service passes AAA authentication (the endpoint is annotated `@AAA`), so the request is accepted.
3. No filter validates `customerId`—the registered filters (`MarketplaceIdValidationFilter`, `ARestMetricsFilter`) only handle marketplace validation and metrics.
4. The review is persisted under the victim's customer identity with arbitrary pet associations.

### Recommendation

Add a customer ownership check in `PetBusinessLogic.submitReviewData` that validates the `customerId` in the review matches the authenticated caller's identity, following the same pattern already used in `deactivatePet`:

```java
public String submitReviewData(PetProductReview petProductReview) {
    // Validate pet ownership before processing tagged pets
    if (petProductReview.getTaggedPets() != null) {
        for (String taggedPet : petProductReview.getTaggedPets()) {
            Pet pet = PetConverter.convertFromIonValue(ionSystem.singleValue(taggedPet));
            Pet existingPet = petDAO.lookupPetById(pet.getPetId());
            if (existingPet != null && !petProductReview.getCustomerId().equals(existingPet.getCustomerId())) {
                throw new NotAuthorizedException(NOT_AUTHORIZED_RESPONSE);
            }
        }
    }
    // ... existing logic ...
}
```

Additionally, introduce a request filter or middleware that extracts the authenticated customer identity from the calling context and validates (or overwrites) the `customerId` field in the request body, so the service does not rely on callers to supply a truthful value. This is especially important given the 160+ services authorized to call this endpoint.


---

## 9. Authentication Bypass in Graffiti Add-to-Cart Endpoint

**CWE:** CWE-863 - Missing or Incorrect Authorization  
**Location:** `src/PetsProfileWebsite/src/com/amazon/pets/profile/website/controller/core/GraffitiController.java:392`  
**Severity:** <span class="severity-text-low">Low</span>  

### Impact

An unauthenticated attacker can invoke the add-to-cart code path by sending a `POST` to `/yourpets/graffiti-add-to-cart`, but a downstream validation in `UberCartV2CartService.validateAddToCartParams()` calls `Validate.notEmpty(customerId, ...)` which throws an `IllegalArgumentException` for the empty customer ID returned by unauthenticated sessions. This exception is caught by `CartController`'s `catch (RuntimeException e)` block before the UberCart backend is ever called, so no cart entries are created and no downstream service resources are consumed. The realistic impact is limited to generating error log entries and incrementing the `ADD_ITEMS_TO_CART_ERROR` metric counter, which at scale could produce log noise and minor metric pollution but no business-state changes.

### Description

The `POST /yourpets/graffiti-add-to-cart` endpoint in `GraffitiController` is missing the `@RequiresAuthenticatedUser` annotation. It delegates directly to `CartController.addItemsToCart()` as a plain Java method call, which bypasses the authentication interceptor that would normally protect that method.

#### How the bypass works

The Horizonte framework enforces `@RequiresAuthenticatedUser` via `RequiresAuthenticatedUserInterceptor`, a Spring MVC `HandlerInterceptor`. This interceptor only inspects the `HandlerMethod` that Spring's `DispatcherServlet` resolved from the incoming URL — it does **not** apply to subsequent Java method calls between Spring beans.

Here is the entry point at line 380–394 of `GraffitiController.java`:

```java
// GraffitiController.java:380-394
@RequiresValidToken(value = "postCsrfTokenValue")                  // CSRF only
@RequestMapping(value = GRAFFITI_ADD_TO_CART, method = RequestMethod.POST)
@PageType(pageType = "pets-profile", subPageType = "graffiti-add-to-cart")
@ResponseBody
public AjaxJSONResponse<String> graffitiAddItemsToCart(final HttpServletRequest request) {
    //route AddToCart request to cart controller
    return cartController.addItemsToCart(request);   // direct Java call
}
```

Compare with the target method in `CartController.java` (lines 52–56), which **does** declare the annotation:

```java
// CartController.java:52-56
@RequiresValidToken(name = "csrfToken", value = "csrfPetAddToCartTokenValue")
@RequestMapping(value = "/yourpets/cart", method = RequestMethod.POST)
@RequiresAuthenticatedUser   // ← present here, but never evaluated on this code path
@PageType(pageType = "pets-profile", subPageType = "cart")
@ResponseBody
public AjaxJSONResponse<String> addItemsToCart(final HttpServletRequest request) { ... }
```

#### Why the impact is bounded

For unauthenticated sessions, `BaseController.getCustomerId()` returns an empty string. Before the UberCart API is invoked, `UberCartV2CartService.validateAddToCartParams()` rejects it:

```java
// UberCartV2CartService.java:196-199
private void validateAddToCartParams(String sessionId, List<CartItem> items, String customerId) {
    Validate.notEmpty(customerId, "Customer Id cannot be empty.");  // throws IllegalArgumentException
    Validate.notEmpty(sessionId, "Session Id cannot be empty.");
    Validate.notEmpty(items, "Product items cannot be empty.");
}
```

The `IllegalArgumentException` propagates back to `CartController`, where it is caught before any UberCart call is made:

```java
// CartController.java:96-98
} catch (RuntimeException e) {
    log.error("Failed to add items to cart for customer {} in session {}.", customerId, sessionId, e);
}
queryLogService.addCount(Metrics.ADD_ITEMS_TO_CART_ERROR, 1, Unit.ONE);
response.setSuccess(false);
return response;
```

### Recommendation

Add `@RequiresAuthenticatedUser` to `graffitiAddItemsToCart()` so the Horizonte interceptor enforces authentication before the handler executes:

```java
@RequiresAuthenticatedUser   // ← add this
@RequiresValidToken(value = "postCsrfTokenValue")
@RequestMapping(value = GRAFFITI_ADD_TO_CART, method = RequestMethod.POST)
@PageType(pageType = "pets-profile", subPageType = "graffiti-add-to-cart")
@ResponseBody
public AjaxJSONResponse<String> graffitiAddItemsToCart(final HttpServletRequest request) {
    return cartController.addItemsToCart(request);
}
```

As defense-in-depth, add an explicit `customerId` emptiness check in `CartController.addItemsToCart()` (mirroring the existing `sessionId` check) so the request is rejected early with a clear log message rather than relying on the downstream `Validate.notEmpty` to throw an exception.


## Appendix A: Entrypoints

| Entrypoint | Args | Return | Exposure |
|------------|------|--------|----------|
| PetsController::addPet | 2 | IonValue | service-to-service |
| PetsController::addPet | 4 | IonValue | service-to-service |
| PetsController::addPet | 6 | IonValue | service-to-service |
| PetsController::updatePet | 2 | IonValue | service-to-service |
| PetsController::updatePet | 3 | IonValue | service-to-service |
| PetsController::getPet | 1 | IonValue | service-to-service |
| PetsController::getPet | 2 | IonValue | service-to-service |
| PetsController::deletePet | 2 | IonValue | service-to-service |
| PetsController::deletePet | 3 | IonValue | service-to-service |
| PetsController::listActivePetsByCustomerId | 1 | IonList | service-to-service |
| PetsController::listActivePetsByCustomerId | 2 | IonList | service-to-service |
| PetsController::listPetsByCustomerIdAndStatus | 3 | IonList | service-to-service |
| PetsController::submitPetReview | 2 | String | service-to-service |
| PetsController::getReviewData | 4 | PetProductReview | service-to-service |
| ActivitiesController::getCustomerSignUpList | 4 | IonList | service-to-service |
| ActivitiesController::getCustomerDropoutList | 4 | IonList | service-to-service |
| ClinicSearchController::searchClinics | 3 | IonValue | service-to-service |
| ClinicSearchController::searchClinics | 4 | IonValue | service-to-service |
| CustomersController::getCustomerSummaryView | 1 | IonValue | service-to-service |
| CustomersController::getCustomerSummaryView | 2 | IonValue | service-to-service |
| FoodAdvisorController::getFoodLifespan | 4 | FoodLifespanResponse | service-to-service |
| FoodAdvisorCustomAAPIController::foodAdvisor | 3 | FoodAdvisorResponse | user |
| PetAcquisitionWidgetCustomAPIController::profileAcquisitionOptOut | 2 | ProfileAcquisitionOptOutResponse | user |
| PetAcquisitionWidgetCustomAPIController::profileAcquisitionCreatePet | 3 | CreatePetProfileResponse | user |
| CustomerGraffitiOptionController::getIsPetProfileGraffitiOptOut | 2 | GraffitiOptOutResponse | service-to-service |
| CustomerGraffitiOptionController::optOutPetProfileGraffiti | 2 | void | service-to-service |
| VetsController::addVet | 1 | IonValue | service-to-service |
| VetsController::addVet | 2 | IonValue | service-to-service |
| VetsController::updateVet | 2 | IonValue | service-to-service |
| VetsController::updateVet | 3 | IonValue | service-to-service |
| VetsController::getVet | 1 | IonValue | service-to-service |
| VetsController::getVet | 2 | IonValue | service-to-service |
| VetsController::deleteVet | 1 | IonValue | service-to-service |
| VetsController::deleteVet | 2 | IonValue | service-to-service |
| VetsController::listVetsByCustomerId | 1 | IonList | service-to-service |
| VetsController::listVetsByCustomerId | 2 | IonList | service-to-service |
| ProductsController::listRecommendedProductByCustomerId | 1 | IonList | service-to-service |
| ProductsController::listRecommendedProductByCustomerId | 2 | IonList | service-to-service |
| PurchasesController::getPetPastPurchasesByCustomerId | 2 | IonList | service-to-service |
| PurchasesController::getPetPastPurchasesByCustomerId | 3 | IonList | service-to-service |
| RecommendationsController::getBuyAgainRecommendations | 1 | IonList | service-to-service |
| RecommendationsController::getBuyAgainRecommendations | 2 | IonList | service-to-service |
| RecommendationsController::getPetSimilarityRecommendations | 1 | IonList | service-to-service |
| RecommendationsController::getPetSimilarityRecommendations | 2 | IonList | service-to-service |
| RecommendationsController::getSWYPRecommendations | 5 | IonList | service-to-service |
| RecommendationsController::getReviewsBasedRecommendations | 3 | ReviewBasedRecommendations | service-to-service |
| RecommendationsController::getPetPersonalizationRecommendations | 5 | IonList | service-to-service |
| RedeemClaimCodeController::redeemClaimCode | 1 | String | service-to-service |
| RedeemClaimCodeController::redeemClaimCode | 2 | String | service-to-service |
| RedeemClaimCodeController::getClaimCodeStatusForCustomer | 1 | String | service-to-service |
| RedeemClaimCodeController::getClaimCodeStatusForCustomer | 2 | String | service-to-service |
| SubscriptionController::subscribeCustomer | 1 | IonBool | service-to-service |
| SubscriptionController::subscribeCustomer | 2 | IonBool | service-to-service |
| SubscriptionController::getCustomerSubscriptionStatus | 1 | IonBool | service-to-service |
| SubscriptionController::getCustomerSubscriptionStatus | 2 | IonBool | service-to-service |
| RemoteStrategyController::getWidgets | 1 | GetWidgetsResponse | service-to-service |
| ProfilePageController::execute | 3 | ModelAndView | user |
| ProfilePageController::profileAdd | 2 | AjaxJSONResponse | user |
| ProfilePageController::profileRemove | 1 | AjaxJSONResponse | user |
| AddPetController::renderAddPetLandingPage | 2 | ModelAndView | user |
| AddPetController::renderAddPetPage | 3 | ModelAndView | user |
| EditPageController::renderEditPage | 2 | ModelAndView | user |
| EditPageController::profileEdit | 2 | AjaxJSONResponse | user |
| EditPageController::changeStatus | 1 | AjaxJSONResponse | user |
| VetSearchController::getClinics | 5 | List | user |
| VetClinicsPageController::execute | 1 | ModelAndView | user |
| VetClinicsPageController::addVetClinic | 1 | AjaxJSONResponse | user |
| VetClinicsPageController::removeVetClinic | 1 | AjaxJSONResponse | user |
| GraffitiController::renderGraffitiWidget | 3 | ModelAndView | service-to-service |
| GraffitiController::dismissGraffitiWidget | 0 | void | user |
| GraffitiController::savePetProfile | 3 | AjaxJSONResponse | user |
| GraffitiController::graffitiAddItemsToCart | 1 | AjaxJSONResponse | user |
| RypController::getRypRemoteWidget | 1 | ModelAndView | user |
| RypController::rypRemoteWidgetPost | 1 | PetsRypReference | user |
| PurchasesSubscriptionsController::execute | 1 | ModelAndView | user |
| CarouselAjaxController::execute | 14 | List | user |
| CartController::addItemsToCart | 1 | AjaxJSONResponse | user |
| DynamicContentLoader::renderPastPurchases | 3 | ModelAndView | user |
| DynamicContentLoader::fetchPastPurchases | 2 | List | user |
| EDXS3MessageConsumer::processMessage | 1 | void | service-to-service |
| ImageDeletionMessageConsumer::processMessage | 1 | void | service-to-service |
| RedemptionPromotionMessageConsumer::processMessage | 1 | void | service-to-service |

## Appendix B: Per-Agent Metrics Breakdown

| Agent | Invocations | Cost | Time | Input Tokens | Output Tokens |
|-------|-------------|------|------|--------------|---------------|
| consolidate | 1 | $0.3890 | 00:03:51 | 339 | 14.0K |
| cvssv4 | 15 | $2.4699 | 00:08:33 | 394.4K | 33.9K |
| deduplicate | 272 | $0.7100 | 01:08:04 | 1.1M | 379.6K |
| entrypoint | 6 | $1.4533 | 00:04:19 | 148.4K | 29.0K |
| ep-analyze | 82 | $4.0833 | 00:21:54 | 2.7M | 891.8K |
| ep-qa | 297 | $82.7638 | 02:48:19 | 9.1M | 1.2M |
| qa | 45 | $18.2991 | 00:28:38 | 2.1M | 236.4K |
| qa-amend | 2 | $0.1588 | 00:01:38 | 18.3K | 4.6K |
| validate | 45 | $8.2558 | 00:31:07 | 2.1M | 325.1K |
| writeup | 15 | $0.7577 | 00:06:57 | 47.5K | 29.1K |
| ws-analyze | 1 | $0.1410 | 00:00:28 | 49.5K | 3.9K |

## Appendix C: Package Commits

| Package | Commit |
|---------|--------|
| src/PetsProfileService | `a4d1eae69770` |
| src/PetsProfileWebsite | `65bb9061409c` |

## Appendix D: Profile Configuration

**Profile:** web

**Profile Description:** Web applications and services

### Entrypoints

| ID | Name |
|----|------|
| EP-WEB-001 | HTTP Request Handlers |
| EP-WEB-002 | Message Queue Consumers |
| EP-WEB-003 | Lambda Functions |
| EP-WEB-004 | GraphQL Resolvers |
| EP-WEB-005 | WebSocket Handlers |
| EP-WEB-006 | Frontend Components |

### CWEs

| ID | Title |
|----|-------|
| CWE-15 | External Control of System or Configuration Setting |
| CWE-22 | Improper Limitation of a Pathname to a Restricted Directory |
| CWE-78 | Improper Neutralization of Special Elements used in an OS Command |
| CWE-79 | Improper Neutralization of Input During Web Page Generation |
| CWE-89 | Improper Neutralization of Special Elements used in an SQL Command |
| CWE-94 | Improper Control of Generation of Code |
| CWE-257 | Storing Passwords in a Recoverable Format |
| CWE-306 | Missing Authentication for Critical Function |
| CWE-307 | Improper Restriction of Excessive Authentication Attempts |
| CWE-310 | Cryptographic Issues |
| CWE-315 | Cleartext Storage of Sensitive Information in a Cookie |
| CWE-319 | Cleartext Transmission of Sensitive Information |
| CWE-352 | Cross-Site Request Forgery |
| CWE-384 | Session Fixation |
| CWE-434 | Unrestricted Upload of File with Dangerous Type |
| CWE-502 | Deserialization of Untrusted Data |
| CWE-526 | Cleartext Storage of Sensitive Information in an Environment Variable |
| CWE-532 | Insertion of Sensitive Information into Log File |
| CWE-537 | Java Runtime Error Message Containing Sensitive Information |
| CWE-601 | URL Redirection to Untrusted Site ('Open Redirect') |
| CWE-611 | Improper Restriction of XML External Entity Reference |
| CWE-614 | Sensitive Cookie in HTTPS Session Without 'Secure' Attribute |
| CWE-656 | Reliance on Security Through Obscurity |
| CWE-668 | Exposure of Resource to Wrong Sphere |
| CWE-776 | Improper Restriction of Recursive Entity References in DTDs ('XML Entity Expansion') |
| CWE-798 | Use of Hard-coded Credentials |
| CWE-863 | Missing or Incorrect Authorization |
| CWE-918 | Server-Side Request Forgery |
| CWE-942 | Permissive Cross-domain Security Policy with Untrusted Domains |
| CWE-1004 | Sensitive Cookie Without 'HttpOnly' Flag |
| CWE-1021 | Improper Restriction of Rendered UI Layers or Frames |

### Exposures

| Name | Description |
|------|-------------|
| Unauthenticated | Publicly accessible with no authentication required |
| User | Requires user/customer authentication but available to regular users |
| Admin | Requires administrative or elevated privileges |
| Service-to-Service | Service-to-service communication requiring trusted service authentication |
| Local | Requires local system access |
