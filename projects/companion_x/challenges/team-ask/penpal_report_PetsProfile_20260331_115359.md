# PenPal Analysis Report

**Analyst:** daweiss
**Generated:** 2026-03-31 11:53:58
**Workspace:** `/local/home/daweiss/PenPalPetsProfile`
**PenPal Version:** 1.3.0b0

> ⚠️ **DISCLAIMER:** PenPal is an experimental AI tool that may miss vulnerabilities, report false positives, or recommend ineffective fixes. It does not replace professional security review. Validate all findings independently. Follow acceptable use policies for projects requiring disclosure.

| Metric | Value |
|--------|-------|
| Assessment Cost | $143.34 |
| Actual Runtime | 10:33:16 |
| GPU Time | 08:29:13 |
| Total Tokens | 54.7M |
| Entrypoints | 59 |
| CWE Checks | 795 |
| Flagged Issues | 91 |
| Dismissed | 67 |
| Plausible | 24 |
| Confirmed Vulnerabilities | 7 |

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
<td class="severity-high">0</td>
<td class="severity-medium">5</td>
<td class="severity-low">2</td>
<td class="severity-total">7</td>
</tr>
</table>


## Security Issues Summary

| ID | Title | Severity | CWE |
|----|-------|----------|-----|
| 26 | Missing Authorization (IDOR) in Vet Clinic Removal Endpoint | **Medium** | CWE-863 |
| 29 | Insertion of Sensitive Information into Log Files Across PetsProfileService and PetsProfileWebsite | **Medium** | CWE-532 |
| 31 | CloudSearch Query Injection in Clinic Search Endpoint | **Medium** | CWE-94 |
| 33 | Cleartext Storage of Sensitive Alexandria Image URL in PetBusinessLogic.setImageData | **Medium** | CWE-310 |
| 32 | Unrestricted MIME Type in Pet Image Upload to Alexandria | **Medium** | CWE-434 |
| 27 | Missing Marketplace Authorization in Vet Search Endpoint | **Low** | CWE-863 |
| 34 | Stored Cross-Site Scripting (XSS) via Unescaped Pet Name in JSP Templates | **Low** | CWE-79 |

## Vulnerability Details

## 1. Missing Authorization (IDOR) in Vet Clinic Removal Endpoint

**CWE:** CWE-863 - Missing or Incorrect Authorization  
**Location:** `PetsProfileWebsite/src/PetsProfileWebsite/src/com/amazon/pets/profile/website/controller/core/VetClinicsPageController.java:208`  
**Severity:** <span class="severity-text-medium">Medium</span>  

### Impact

Any authenticated customer can delete another customer's vet clinic association by supplying that customer's `vetId` in a POST to `/yourpets/vet/remove`, because no layer in the call chain verifies that the authenticated user owns the targeted vet record. The attack is bounded by the requirement that the attacker must know or guess a valid UUID-format `vetId` belonging to the victim, and both users must share the same marketplace. A successful exploit soft-deletes the victim's vet clinic entry (sets status to `INACTIVE`), silently removing it from their pets profile with no indication of tampering. Because the deletion is a state change persisted to DynamoDB, the victim loses their vet clinic data until manual recovery.

### Description

The `removeVetClinic` handler at line 208 accepts a user-supplied `vetId` parameter and passes it through the service layer to the backend deletion logic without ever verifying that the authenticated customer owns that vet record.

#### Controller — No Customer ID Passed

```java
// VetClinicsPageController.java:208
@RequestMapping(value = "/yourpets/vet/remove", method = RequestMethod.POST)
@RequiresAuthenticatedUser
@RequiresValidToken(name = "csrfToken", value = "removeVetClinicCsrfTokenValue")
@ResponseBody
public AjaxJSONResponse<String> removeVetClinic(final HttpServletRequest request) {
    AjaxJSONResponse<String> response = new AjaxJSONResponse<>();

    final String vetId = request.getParameter("vetId");        // attacker-controlled
    if (Objects.nonNull(vetId) && !vetId.trim().isEmpty()) {
        petsProfileService.removeVetClinic(vetId, getEncryptedMarketplaceId());
        // ↑ getCustomerId() is available from BaseController but never passed
        response.setSuccess(true);
        response.setResult(REMOVE_VET_CLINIC_SUCCESS);
    }
    // ...
}
```

`getCustomerId()` resolves the authenticated user's identity via `CustomerId.resolveCurrent()` and is used elsewhere in this controller, but is never passed into the removal flow.

#### Business Logic — Marketplace-Only Check

The backend `VetBusinessLogic::deleteVet` looks up the vet by its ID and only validates the marketplace:

```java
// VetBusinessLogic.java:57+
public Vet deleteVet(final String vetId, final String encryptedMarketplaceId) {
    Vet existingVet = vetDAO.lookupVetById(vetId);  // unscoped — returns any customer's vet
    if (null != existingVet
        && encryptedMarketplaceId.equals(existingVet.getEncryptedMarketplaceId())) {
        existingVet.setStatus(PetProfileStatus.INACTIVE.name());  // soft-delete
        vetDAO.saveVet(existingVet);
        return existingVet;
    }
    // ...
}
```

The `VetModel` stores a `customerId` field as a DynamoDB index hash key, so the ownership data is present on the retrieved record — it is simply never compared against the caller's identity.

#### Contrast with Secure Pattern in the Same Controller

The `addVetClinic` method in the same class correctly scopes its query to the authenticated customer:

```java
List<Vet> customerVetsList = listVetsByCustomerId();  // calls getCustomerId()
```

`removeVetClinic` omits this ownership verification entirely, making it an inconsistency in the same file.

### Recommendation

Add an ownership check in `VetBusinessLogic::deleteVet` that compares the vet record's `customerId` against the authenticated caller's customer ID. This requires threading the customer ID from the controller through the service layer.

In the controller, pass the customer ID into the service call:

```java
// VetClinicsPageController.java — removeVetClinic
petsProfileService.removeVetClinic(vetId, getCustomerId(), getEncryptedMarketplaceId());
```

Update `PetsProfileServiceImpl::removeVetClinic` to accept and forward the customer ID, then add the authorization check in `VetBusinessLogic::deleteVet`:

```java
// VetBusinessLogic.java — deleteVet
Vet existingVet = vetDAO.lookupVetById(vetId);
if (null != existingVet
    && encryptedMarketplaceId.equals(existingVet.getEncryptedMarketplaceId())
    && customerId.equals(existingVet.getCustomerId())) {   // ← ownership check
    existingVet.setStatus(PetProfileStatus.INACTIVE.name());
    vetDAO.saveVet(existingVet);
    return existingVet;
} else {
    throw new IllegalArgumentException("Cannot find vet with vetId " + vetId);
}
```

Ensure the error path returns the same generic message regardless of whether the vet ID doesn't exist or belongs to another customer, to avoid leaking existence information.


---

## 2. Insertion of Sensitive Information into Log Files Across PetsProfileService and PetsProfileWebsite

**CWE:** CWE-532 - Insertion of Sensitive Information into Log File  
**Location:** `Workspace:N/A`  
**Severity:** <span class="severity-text-medium">Medium</span>  

### Impact

Any user or system with read access to production log files or log aggregation infrastructure (e.g., CloudWatch Logs, Splunk) can extract live Alexandria content retrieval tokens from `AlexandriaDownloader.java` and use them to download pet profile images before token expiry — effectively turning the log store into a credential oracle for the image-download service. The same log access yields raw session IDs from `CartController.java`, which an attacker could replay to hijack active customer sessions and perform cart or account actions on their behalf, constrained only by the session's remaining TTL and scope.

On every pet-update failure, the full `PetInfo` object — customer ID, pet name, breed, gender, full birth date, weight, and description — is serialized into production error logs via `EditPageController.java`. This is not a single-field leak; it is a complete personal profile written in bulk on an error path that any transient service fault can trigger, creating ongoing PII accumulation in log storage subject to data protection obligations (GDPR, CCPA). Additionally, abandoned diagnostic code in `GraffitiController.java` logs customer IDs and marketplace IDs on every widget render at INFO level, creating a high-volume stream of customer identifiers in production logs that was never intended to ship.

### Description

Multiple production-active code paths write authentication credentials, session tokens, and rich PII directly into application log files. The log-level configurations confirm these statements fire in production: `PetsProfileService` sets `com.amazon.pets` to `INFO`, and `PetsProfileWebsite` sets it to `DEBUG`.

#### Authentication Token Logged Verbatim

In `AlexandriaDownloader.java` at line 95, the full Alexandria content retrieval token is logged at INFO on every image download:

```java
// AlexandriaDownloader.java:95
String token = alexandriaDocumentManagerServiceClient
        .newCreateContentRetrievalTokenCall()
        .call(tokenRequest)
        .getContentToken();
log.info("Obtained token={} for downloading.", token);
```

This token is a short-lived credential granting access to a specific document in Alexandria. Because `com.amazon.pets` is at INFO in the production config (`log4j2-prod.xml`), this statement executes on every pet image download request.

#### Session ID Logged on Error Path

In `CartController.java` at line 97, the customer's session ID is logged alongside their customer ID when a cart operation fails:

```java
// CartController.java:97
log.error("Failed to add items to cart for customer {} in session {}.", customerId, sessionId, e);
```

`sessionId` is resolved via `SessionId.resolveCurrent()` — the platform session token for the active user. ERROR level is always active, so any cart-add failure writes a replayable session credential to disk.

#### Full PetInfo PII Object Serialized to Logs

In `EditPageController.java` at line 355, the entire `PetInfo` model is serialized via Lombok's `@Data`-generated `toString()`:

```java
// EditPageController.java:355
log.error("update pet failed for customer: {}, with petInfo: {}", customerId, newPetInfo.toString(), e);
```

`PetInfo` (annotated `@Data` at line 27 of `PetInfo.java`) includes 30+ fields:

```java
private String customerId;
private String petId;
private String name;
private String breed;
private String gender;
private String description;
private int birthMonth;
private int birthYear;
private int birthDay;
private String birthDate;
private int weightValue;
private String weightUnit;
// ... additional fields
```

Every pet-update error dumps this complete personal profile into production logs.

#### Abandoned Diagnostic Code Logging All Widget Arguments

In `GraffitiController.java` at lines 177–180, a loop logs every key-value pair in the `widgetArgs` map at INFO level — including `customerId` (constant at line 111) and `marketplaceID` (constant at line 112):

```java
// GraffitiController.java:177-180
// Currently, we don't know which magic parameters will be passed through from RetailWebsite and used.
// Logging them out for the experiment. We will remove this once we decide what metrics to use.
for (Map.Entry<String, String> e: widgetArgs.entrySet()) {
    log.info("key: {}, value: {}", e.getKey(), e.getValue());
}
```

The inline comment confirms this was intended as temporary code that was never removed. With the website's `com.amazon.pets` threshold at `DEBUG`, this INFO statement fires on every Graffiti widget render in all environments.

### Recommendation

Remove or redact each sensitive value at its log call site. Do not rely on log-level changes as a fix — levels shift between environments and deployments, and ERROR-level statements are always active.

**`AlexandriaDownloader.java:95`** — Remove the token value entirely. A boolean confirmation is sufficient:

```java
log.info("Obtained content retrieval token for downloading.");
```

**`CartController.java:97`** — Remove `sessionId` from the log statement. The customer ID and exception stack trace are sufficient for debugging:

```java
log.error("Failed to add items to cart for customer {}.", customerId, e);
```

**`EditPageController.java:355`** — Replace the full `PetInfo.toString()` dump with a minimal identifier. Only `petId` is needed for debugging:

```java
log.error("update pet failed for customer: {}, petId: {}", customerId, newPetInfo.getPetId(), e);
```

Additionally, annotate `PetInfo` to prevent accidental future serialization of PII fields:

```java
@ToString(onlyExplicitlyIncluded = true)
public class PetInfo {
    @ToString.Include private String petId;
    // other fields excluded from toString by default
}
```

**`GraffitiController.java:177–180`** — Delete the entire diagnostic loop and its comment. It is explicitly marked as temporary and serves no production purpose.

As a follow-up hardening step, audit the remaining ~40 customer ID log statements listed in the service (e.g., `PetsController.java`, `BaseController.java`, `VetClinicsPageController.java`) and evaluate whether each is necessary or can be replaced with a non-reversible identifier such as a truncated hash.


---

## 3. CloudSearch Query Injection in Clinic Search Endpoint

**CWE:** CWE-94 - Improper Control of Generation of Code  
**Location:** `PetsProfileService/src/PetsProfileService/src/com/amazon/pets/profileservice/resource/ClinicSearchController.java:36`  
**Severity:** <span class="severity-text-medium">Medium</span>  

### Impact

An authenticated internal service can inject CloudSearch structured query syntax through the `query` parameter of the clinic search endpoint, breaking out of the intended quoted-string context to manipulate query logic—though exploitation is bounded by the CloudAuth requirement and the fact that the underlying CloudSearch index contains only public veterinary clinic business data (name, address, phone number, coordinates). The most likely real-world outcome is causing CloudSearch query parse errors (HTTP 400), which partially denies clinic search functionality for crafted inputs. A more sophisticated injection could widen search filters to return unintended result sets, but the data returned remains non-sensitive public business information. No customer PII, financial data, or private records are reachable through this index.

### Description

The `searchClinics` endpoint in `ClinicSearchController` accepts a `query` string and passes it through to `ClinicBusinessLogic.search()` where it is split into tokens and embedded directly into CloudSearch structured query expressions without escaping special characters.

#### Tainted Data Flow

The `query` parameter enters at the REST endpoint:

```java
// ClinicSearchController.java:50
ClinicSearchResult clinicSearchResult = clinicBusinessLogic.search(query, start, size);
```

In `ClinicBusinessLogic.search()`, the only transformation is replacing `+` with a space—no sanitization of query-syntax characters occurs:

```java
// ClinicBusinessLogic.java:58-67
public ClinicSearchResult search(String query, long start, long size) {
    query = replacePlus(query);  // Only replaces '+' with ' '
    ClinicSearchResult result = searchV2(query, start, size);
    ...
}
```

The query is then split on whitespace (`query.trim().split("\\s+")`), and tokens that are not recognized as US state codes or 5-digit zipcodes are classified as "other terms." These terms are injected directly into `getOrTermQuery()`:

```java
// ClinicBusinessLogic.java:161,165
termQueries.addAll(terms.stream()
    .map((t) -> String.format("(term boost=3 field=name '%s')", t))
    .collect(Collectors.toList()));

termQueries.addAll(terms.stream()
    .map((t) -> String.format("(term boost=2 field=city '%s')", t))
    .collect(Collectors.toList()));
```

A single quote (`'`) in any term breaks the string delimiter boundary in the CloudSearch structured query DSL. For example, the input `clinic' WA` splits into tokens `["clinic'", "WA"]`. `"WA"` is classified as a state, but `"clinic'"` is an "other term" and produces:

```
(term boost=3 field=name 'clinic'')
```

The unmatched quote corrupts the query structure, and more carefully crafted payloads could inject arbitrary CloudSearch operators (`or`, `and`, `term`, `field=`) to alter query semantics.

#### Why the zipcode/state sinks are safe

The `getZipcodeOrStateQuery()` method also embeds values with `String.format`, but the upstream classification logic validates that states match a whitelist of 2-letter codes (`isState()`) and zipcodes are exactly 5 digits (`isFiveDigits()`), so no special characters can reach those sinks.

#### Existing fix pattern in the codebase

The same codebase already escapes apostrophes in the food product search path via `SearchGatewayQueryBuilderImpl`:

```java
// SearchGatewayQueryBuilderImpl.java:252
private static String escapeApostrophes(String string) {
    return StringUtils.replace(string, "'", "\\'");
}
```

This identical escaping was not applied to the clinic search path in `ClinicBusinessLogic.getOrTermQuery()`.

### Recommendation

Escape single quotes in every user-supplied term before embedding it in the CloudSearch structured query. Apply the same `escapeApostrophes` pattern already used in `SearchGatewayQueryBuilderImpl` to the terms in `getOrTermQuery()`:

```java
// ClinicBusinessLogic.java — getOrTermQuery()
termQueries.addAll(terms.stream()
    .map((t) -> String.format("(term boost=3 field=name '%s')", escapeSingleQuotes(t)))
    .collect(Collectors.toList()));

termQueries.addAll(terms.stream()
    .map((t) -> String.format("(term boost=2 field=city '%s')", escapeSingleQuotes(t)))
    .collect(Collectors.toList()));

// Add this utility method to ClinicBusinessLogic
private static String escapeSingleQuotes(String input) {
    return StringUtils.replace(input, "'", "\\'");
}
```

As a follow-up hardening step, consider adding input validation at the `ClinicSearchController` level to reject or strip characters that have no legitimate use in a clinic name or city search (e.g., parentheses, colons) before they reach the business logic layer.


---

## 4. Cleartext Storage of Sensitive Alexandria Image URL in PetBusinessLogic.setImageData

**CWE:** CWE-310 - Cryptographic Issues  
**Location:** `PetsProfileService/src/PetsProfileService/src/com/amazon/pets/profileservice/resource/PetsController.java:204`  
**Severity:** <span class="severity-text-medium">Medium</span>  

### Impact

An attacker or insider with read access to the DynamoDB table (via direct table access, database backups, or administrative tooling) can retrieve pre-signed Alexandria image URLs that embed time-limited authentication tokens granting access to RED-classified customer pet images. Because the URLs are stored and returned in plaintext, the window of exposure extends from initial storage until the URL's expiration — and is compounded by the `savePet` method at `PetDAOImpl.java:85` logging the full pet IonStruct (`pet.getIonStruct().toPrettyString()`), which writes these sensitive URLs into application logs where they may persist indefinitely and be accessible through log aggregation systems. The CloudAuth service-to-service protection on the `getPet` endpoint limits direct API-level exploitation, but it does not protect the data at rest in DynamoDB or in logs, which are the primary exposure surfaces.

### Description

#### Incomplete Encryption Implementation

The `setImageData` method in `PetBusinessLogic.java` was clearly designed to encrypt the Alexandria image URL — the `ServiceMetrics` instance is named `"PetsBusinessLogic_EncryptImageUri"` — but the encryption was never implemented. The URL from Alexandria (a pre-signed URL containing embedded authentication tokens for accessing RED-classified customer images) is stored in plaintext.

```java
// PetBusinessLogic.java:501-512
private void setImageData(String documentVersionId, AlexandriaDocumentDownloadResponse documentResponse, Pet pet) {
    ServiceMetrics metrics = new ServiceMetrics("PetsBusinessLogic_EncryptImageUri"); // <-- encryption was intended
    ImageData imageData = pet.getImageData();
    //NOTE: Not saving image content data, as it is classified RED
    imageData.setEncryptedImageContent("");
    imageData.setExpirationDate(documentResponse.getImageUrlExpirationDateTime());
    imageData.setAlexandriaImageUrl(documentResponse.getImageUrl());  // <-- stored in plaintext
    log.info("set image document version id {}, setting the imageURI", imageData.getDocumentId());
    metrics.commit();
}
```

Note the contradiction: `encryptedImageContent` is explicitly cleared because the content is "classified RED," yet the Alexandria image URL — which contains authentication tokens that grant access to that same RED content — is stored without any encryption.

#### Data Flow from API to Plaintext Storage

The `getPet` endpoint in `PetsController.java` triggers this flow when the image URL has expired or is missing:

```java
// PetsController.java:213-227
public IonValue getPet(final String petId, final String encryptedMarketplaceId) {
    // ...
    Pet pet = petBusinessLogic.getPet(petId, true, encryptedMarketplaceId);  // needImageUrlUpdate=true
    if (null != pet) {
        IonValue result = PetConverter.convertToIonValue(pet);  // URL returned in plaintext
        return result;
    }
```

Inside `PetBusinessLogic.getPet` (line 222), the call with `needImageUrlUpdate=true` triggers `handleImageUrlUpdate` (line 229), which calls `saveNewPetImageData` (line 249) when the URL is new or expired. This in turn calls `setImageData` (line 482) and then persists the pet to DynamoDB via `petDAO.savePet(pet, false)` (line 485) — all without encrypting the URL.

#### Log Exposure

After persisting, `PetDAOImpl.savePet` logs the entire pet object including the plaintext URL:

```java
// PetDAOImpl.java:85
log.info("successfully saved the pet for petId {} with data: " + pet.getIonStruct().toPrettyString(), pet.getPetId());
```

This writes the pre-signed Alexandria URL into application logs, extending its exposure beyond DynamoDB into log aggregation and archival systems.

### Recommendation

Encrypt the Alexandria image URL using `keyMaster` before storing it, consistent with the existing pattern used for `petName` encryption elsewhere in the codebase. Update `setImageData` to accept a `KeyMaster` instance and encrypt the URL:

```java
private void setImageData(String documentVersionId, AlexandriaDocumentDownloadResponse documentResponse, Pet pet, KeyMaster keyMaster) {
    ServiceMetrics metrics = new ServiceMetrics("PetsBusinessLogic_EncryptImageUri");
    ImageData imageData = pet.getImageData();
    imageData.setEncryptedImageContent("");
    imageData.setExpirationDate(documentResponse.getImageUrlExpirationDateTime());

    String encryptedUrl = keyMaster.encrypt(documentResponse.getImageUrl());
    imageData.setAlexandriaImageUrl(encryptedUrl);

    log.info("set image document version id {}, setting the imageURI", imageData.getDocumentId());
    metrics.commit();
}
```

Correspondingly, decrypt the URL when reading it back in the response path (e.g., in `PetConverter.convertToIonValue` or at the point of use).

Additionally, sanitize the log statement in `PetDAOImpl.java:85` to avoid logging the full pet IonStruct. Replace it with a log that only includes the `petId`, or redact sensitive fields before logging.


---

## 5. Unrestricted MIME Type in Pet Image Upload to Alexandria

**CWE:** CWE-434 - Unrestricted Upload of File with Dangerous Type  
**Location:** `PetsProfileService/src/PetsProfileService/src/com/amazon/pets/profileservice/resource/PetsController.java:173`  
**Severity:** <span class="severity-text-medium">Medium</span>  

### Impact

A compromised or malicious internal service with CloudAuth credentials can upload files to Alexandria with an arbitrary attacker-controlled MIME type (e.g., `text/html`, `application/javascript`) by setting the `imageContentType` field in the `updatePet` request body to any string value. If Alexandria serves these stored files back to browsers using the declared Content-Type, this enables stored cross-site scripting — an attacker uploads an HTML document disguised as a pet image, and any user or service that later fetches that "image" via a browser could execute the embedded script. The attack requires high privileges (CloudAuth service-to-service authentication) and the image content itself must be KMS-encrypted, which bounds the attack surface to internal callers capable of producing valid encrypted blobs. The integrity impact extends to the downstream Alexandria storage system, which will persist and potentially serve files with dangerous types it was never intended to host.

### Description

The `updatePet` endpoint accepts an `IonValue` body containing pet profile data, including image metadata. The `imageContentType` field within `ImageData` flows from untrusted input all the way to the Alexandria file upload request without any validation against an allowlist of safe image MIME types.

#### Unvalidated Input at Entry Point

At `PetsController.java:173`, the incoming `petIon` is structurally validated by `PetConverter.isValidPetIon()`, which only checks Ion schema structure — it does not inspect or constrain the value of `imageContentType`:

```java
// PetsController.java:173-190
public IonValue updatePet(final String petId, final IonValue petIon, final String encryptedMarketplaceId) {
    if (!PetConverter.isValidPetIon(petIon, false)) {  // structural validation only
        throw new BadRequestException("petIon is not valid");
    }
    // ...
    Pet pet = PetConverter.convertFromIonValue(petIon);           // line 189
    petBusinessLogic.updatePetInfo(pet, encryptedMarketplaceId);  // line 190
```

#### Null-Only Check Before Upload

In `PetImageAlexandriaService.java`, the only gate before uploading is `hasRequiredImageInputFieldsToUpload()`, which performs a null check and nothing else:

```java
// PetImageAlexandriaService.java:164-168
private boolean hasRequiredImageInputFieldsToUpload(Pet pet) {
    return (pet.getImageData() != null
           && pet.getImageData().getEncryptedImageContent() != null
           && pet.getImageData().getImageContentType() != null   // null check only
           && pet.getCustomerId() != null
           && pet.getPetId() != null);
}
```

#### Attacker-Controlled MIME Type Reaches Upload

The `imageContentType` string is read directly from the deserialized `Pet` object and set as the MIME type on the Alexandria upload request with no sanitization:

```java
// PetImageAlexandriaService.java:188-194
String contentType = imageData.getImageContentType();  // attacker-controlled
AlexandriaDocumentUploadRequest request = AlexandriaDocumentUploadRequest.builder()
    .document(imageInputStream)
    .mimeType(contentType)  // passed directly
    .build();
```

This value is then used to construct the HTTP multipart Content-Type header sent to Alexandria:

```java
// AlexandriaUploadRequestCreator.java:72-73
builder.addPart(AlexandriaConstants.FILE_FORM_FIELD_NAME,
    new ByteArrayBody(IOUtils.toByteArray(request.getDocument()),
        ContentType.create(request.getMimeType()),  // arbitrary MIME type
        AlexandriaConstants.FILE_FORM_FIELD_NAME));
```

Existing unit tests confirm arbitrary values pass through without error — `"png"` (not even a valid MIME format) in `PetImageAlexandriaServiceTest` and `"testMimeType"` in `AlexandriaUploadRequestCreatorTest`.

### Recommendation

Add an allowlist check for `imageContentType` before the image upload proceeds. The most targeted location is inside `hasRequiredImageInputFieldsToUpload()` in `PetImageAlexandriaService.java`, since it already gates the upload path:

```java
private static final Set<String> ALLOWED_IMAGE_TYPES = Set.of(
    "image/jpeg", "image/png", "image/gif", "image/webp"
);

private boolean hasRequiredImageInputFieldsToUpload(Pet pet) {
    return (pet.getImageData() != null
           && pet.getImageData().getEncryptedImageContent() != null
           && pet.getImageData().getImageContentType() != null
           && ALLOWED_IMAGE_TYPES.contains(pet.getImageData().getImageContentType().toLowerCase())
           && pet.getCustomerId() != null
           && pet.getPetId() != null);
}
```

Callers that fail this check should receive an explicit error. In `uploadPetImageData()`, throw a `BadRequestException` with a message listing the accepted types so callers can self-correct.

As a hardening measure, consider also validating that the decrypted image content's magic bytes (file signature) match the declared MIME type before uploading to Alexandria.


---

## 6. Missing Marketplace Authorization in Vet Search Endpoint

**CWE:** CWE-863 - Missing or Incorrect Authorization  
**Location:** `PetsProfileWebsite/src/PetsProfileWebsite/src/com/amazon/pets/profile/website/controller/core/VetSearchController.java:29`  
**Severity:** <span class="severity-text-low">Low</span>  

### Impact

The practical impact of this finding is minimal because the marketplace scoping was never implemented in the search backend — every authenticated user already receives identical, global US-only vet clinic results (name, address, phone number) regardless of which `encryptedMarketplaceID` is supplied. This means an attacker who manipulates the marketplace ID in the URL path gains no differential data access; they see the same public directory information they would see with their own session's marketplace. The data itself is classified as Public (vet clinic business listings), not Confidential or Highly Confidential customer data, further bounding the risk. The vulnerability is a genuine missing authorization check on a user-controlled resource scope parameter, but because the parameter is silently discarded before query execution, there is no exploitable consequence today. The risk becomes material only if a future change implements marketplace-based filtering in the search backend without adding the missing authorization guard at the controller layer.

### Description

The `/yourpets/vetsearch` endpoint allows an authenticated user to supply an arbitrary `encryptedMarketplaceID` via the URL path, but no layer in the call chain verifies the user is authorized to query that marketplace. The parameter flows through three layers before being silently dropped.

#### User-Controlled Marketplace Selection

In `VetSearchController.java`, the endpoint accepts an optional path variable. When a user supplies a value, it is used directly — the session-derived fallback only applies when the variable is absent or empty:

```java
// VetSearchController.java:32-45
@RequestMapping(value = {"/yourpets/vetsearch/{encryptedMarketplaceID}", "/yourpets/vetsearch"}, method = RequestMethod.GET)
@RequiresAuthenticatedUser
@ResponseBody
public List<Clinic> getClinics(
    @PathVariable(value = "encryptedMarketplaceID", required = false) String encryptedMarketplaceID, ...) {

    if (Objects.isNull(encryptedMarketplaceID) || encryptedMarketplaceID.isEmpty()) {
        encryptedMarketplaceID = getEncryptedMarketplaceId(); // session fallback
    }
    // ...
    List<Clinic> clinics = petsProfileService.getVetClinics(query, start, size, encryptedMarketplaceID);
```

The `@RequiresAuthenticatedUser` annotation confirms the user is logged in but performs **no check** on whether the user belongs to the requested marketplace.

#### Parameter Silently Dropped

`PetsProfileServiceImpl.getVetClinics()` forwards the marketplace ID unchanged to `ClinicSearchController.searchClinics()`, which accepts the parameter but never passes it to the business logic:

```java
// ClinicSearchController.java:37-50
@Override
public IonValue searchClinics(final String query, final String startString,
        final String sizeString, final String encryptedMarketplaceId) {
    // ... parsing start/size ...
    // encryptedMarketplaceId is NEVER forwarded:
    ClinicSearchResult clinicSearchResult = clinicBusinessLogic.search(query, start, size);
}
```

`ClinicBusinessLogic.search(String, long, long)` has no marketplace parameter at all — it queries CloudSearch globally with only `query`, `start`, and `size`.

### Recommendation

Add an authorization check in `VetSearchController.getClinics()` that validates the user-supplied `encryptedMarketplaceID` matches the user's session marketplace **before** forwarding the request to the service layer. Reject mismatches with an HTTP 403:

```java
// VetSearchController.java — after resolving encryptedMarketplaceID
String sessionMarketplaceId = getEncryptedMarketplaceId();
if (encryptedMarketplaceID != null && !encryptedMarketplaceID.isEmpty()
        && !encryptedMarketplaceID.equals(sessionMarketplaceId)) {
    throw new ResponseStatusException(HttpStatus.FORBIDDEN,
        "Not authorized to query the requested marketplace");
}
// Use the session-derived value as the canonical source of truth
encryptedMarketplaceID = sessionMarketplaceId;
```

As a follow-up, if marketplace-scoped results are eventually needed, pass the validated marketplace ID through to `ClinicBusinessLogic.search()` and include it as a filter in the CloudSearch query to enforce data isolation at the query layer as well.


---

## 7. Stored Cross-Site Scripting (XSS) via Unescaped Pet Name in JSP Templates

**CWE:** CWE-79 - Improper Neutralization of Input During Web Page Generation  
**Location:** `PetsProfileWebsite/src/com/amazon/pets/profile/website/controller/core/EditPageController.java`  
**Severity:** <span class="severity-text-low">Low</span>  

### Impact

An authenticated Amazon customer can store a JavaScript payload in their pet's name via the `/yourpets/edit` form, and it executes in their own browser when they view their pet profile at `/yourpets`. This is self-XSS: the `ProfilePageController.execute()` method loads pets via `listPetsByCustomerId()`, which resolves the customer ID from the current session (`CustomerId.resolveCurrent()`), so pet names are only ever rendered back to the customer who created them — there is no URL or controller that exposes one customer's pet name to another customer. Because the payload is persisted in the database, it fires on every subsequent page load of the customer's own profile. Exploiting this against another user would require social engineering the victim into logging into the attacker's Amazon account and navigating to `/yourpets`, which is not a realistic attack scenario. The code defect is real and should be fixed as defense-in-depth — the same codebase already uses `<c:out>` in other templates, and unescaped output could become exploitable if pet names are ever surfaced in cross-customer contexts (e.g., recommendations, support workflows, or shared wishlists).

### Description

#### Unsanitized Input Path

The attack begins at the user-facing `EditPageController.profileEdit()` endpoint (`/yourpets/edit`, POST), which is accessible to any authenticated Amazon customer (`@RequiresAuthenticatedUser`). The `extractName()` method in `PetInfo` processes the pet name:

```java
// PetInfo.java:97
this.setName(extractName(petsProfileDataSifCrypter, request, "encryptedName"));
```

```java
private String extractName(...) {
    String petName = request.getParameter(fieldName);
    petName = petsProfileDataSifCrypter.decrypt(petName);
    return StringEscapeUtils.unescapeHtml(petName); // DECODES HTML entities — opposite of sanitization
}
```

`PetsProfileDataSifCrypter.decrypt()` is a no-op that returns its input unchanged. `StringEscapeUtils.unescapeHtml()` actively *decodes* HTML entities, meaning even a cautiously encoded payload like `&lt;script&gt;` is converted back to `<script>`. The validator (`PetValidator.isNameValid()`) only checks length (≤200 chars) and a digit pattern — no HTML filtering. The unsanitized name is persisted verbatim to the database.

#### Unescaped Rendering in JSP Templates

When the customer views their pet profile, the stored name is rendered directly into HTML without escaping in multiple templates:

```jsp
<!-- petSummary/desktop.jsp:13, petSummary/tablet.jsp:13 -->
<a:text textSize="${'base_plus'}" textBold="${'true'}">${pet.name}</a:text>

<!-- profile.jsp:108 -->
<span class="pet-name-text-truncate"><a:text textWeight="${'bold'}">${pet.name}</a:text></span>

<!-- removePet/desktop.jsp:225, removePet/tablet.jsp:225, removePet/mobile.jsp:220 -->
<a:paragraph textSize="${'large'}" textAlign="${'center'}">
    ${pet.name}
</a:paragraph>
```

JSP Expression Language (`${pet.name}`) does not auto-escape HTML. Other templates in the same codebase correctly use `<c:out>` to escape the same value:

```jsp
<!-- selectOtherPetsGrid/desktop.jsp:46 — correctly escaped -->
<a:text textSize="${'mini'}" textBold="true"><c:out value="${pet.name}"/></a:text>
```

This inconsistency confirms these locations were missed during prior XSS remediation passes (the git history shows explicit XSS fixes in commits `c4b90d02` and `b7aadcfd`, and the unsafe pattern was reintroduced during an i18n migration in commit `76b99d0e`).

### Recommendation

Replace every unescaped `${pet.name}` in JSP templates with `<c:out value="${pet.name}"/>`, which HTML-encodes the output by default. The specific files to fix:

```jsp
<!-- petSummary/desktop.jsp:13 and petSummary/tablet.jsp:13 -->
<a:text textSize="${'base_plus'}" textBold="${'true'}"><c:out value="${pet.name}"/></a:text>

<!-- profile.jsp:108 -->
<span class="pet-name-text-truncate"><a:text textWeight="${'bold'}"><c:out value="${pet.name}"/></a:text></span>

<!-- removePet/desktop.jsp:225, removePet/tablet.jsp:225, removePet/mobile.jsp:220 -->
<a:paragraph textSize="${'large'}" textAlign="${'center'}">
    <c:out value="${pet.name}"/>
</a:paragraph>
```

Audit all other JSP files for any remaining bare `${pet.*}` expressions and apply the same fix. Also remove the `StringEscapeUtils.unescapeHtml()` call in `PetInfo.extractName()` — it actively reverses HTML encoding and serves no useful purpose given the no-op decrypter.


## Appendix A: Entrypoints

| Entrypoint | Args | Return | Exposure |
|------------|------|--------|----------|
| RemoteStrategyController::getWidgets | 1 | GetWidgetsResponse | service-to-service |
| PetsController::addPet | 6 | IonValue | service-to-service |
| PetsController::updatePet | 3 | IonValue | service-to-service |
| PetsController::getPet | 2 | IonValue | service-to-service |
| PetsController::deletePet | 3 | IonValue | service-to-service |
| PetsController::listActivePetsByCustomerId | 2 | IonList | service-to-service |
| PetsController::listPetsByCustomerIdAndStatus | 3 | IonList | service-to-service |
| PetsController::submitPetReview | 2 | String | service-to-service |
| PetsController::getReviewData | 4 | PetProductReview | service-to-service |
| VetsController::addVet | 2 | IonValue | service-to-service |
| VetsController::updateVet | 3 | IonValue | service-to-service |
| VetsController::getVet | 2 | IonValue | service-to-service |
| VetsController::deleteVet | 2 | IonValue | service-to-service |
| VetsController::listVetsByCustomerId | 2 | IonList | service-to-service |
| CustomersController::getCustomerSummaryView | 2 | IonValue | service-to-service |
| ActivitiesController::getCustomerSignUpList | 4 | IonList | service-to-service |
| ActivitiesController::getCustomerDropoutList | 4 | IonList | service-to-service |
| RecommendationsController::getBuyAgainRecommendations | 2 | IonList | service-to-service |
| RecommendationsController::getPetSimilarityRecommendations | 2 | IonList | service-to-service |
| RecommendationsController::getSWYPRecommendations | 5 | IonList | service-to-service |
| RecommendationsController::getReviewsBasedRecommendations | 3 | ReviewBasedRecommendations | service-to-service |
| RecommendationsController::getPetPersonalizationRecommendations | 5 | IonList | service-to-service |
| SubscriptionController::subscribeCustomer | 2 | IonBool | service-to-service |
| SubscriptionController::getCustomerSubscriptionStatus | 2 | IonBool | service-to-service |
| RedeemClaimCodeController::redeemClaimCode | 2 | String | service-to-service |
| RedeemClaimCodeController::getClaimCodeStatusForCustomer | 2 | String | service-to-service |
| ProductsController::listRecommendedProductByCustomerId | 2 | IonList | service-to-service |
| PurchasesController::getPetPastPurchasesByCustomerId | 3 | IonList | service-to-service |
| ClinicSearchController::searchClinics | 4 | IonValue | service-to-service |
| CustomerGraffitiOptionController::getIsPetProfileGraffitiOptOut | 2 | GraffitiOptOutResponse | service-to-service |
| CustomerGraffitiOptionController::optOutPetProfileGraffiti | 2 | void | service-to-service |
| FoodAdvisorController::getFoodLifespan | 4 | FoodLifespanResponse | service-to-service |
| ProfilePageController::execute | 3 | ModelAndView | user |
| ProfilePageController::profileAdd | 2 | AjaxJSONResponse | user |
| ProfilePageController::profileRemove | 1 | AjaxJSONResponse | user |
| EditPageController::renderEditPage | 2 | ModelAndView | user |
| EditPageController::profileEdit | 2 | AjaxJSONResponse | user |
| EditPageController::changeStatus | 1 | AjaxJSONResponse | user |
| AddPetController::renderAddPetLandingPage | 2 | ModelAndView | user |
| AddPetController::renderAddPetPage | 3 | ModelAndView | user |
| VetClinicsPageController::execute | 1 | ModelAndView | user |
| VetClinicsPageController::addVetClinic | 1 | AjaxJSONResponse | user |
| VetClinicsPageController::removeVetClinic | 1 | AjaxJSONResponse | user |
| VetSearchController::getClinics | 5 | List | user |
| PurchasesSubscriptionsController::execute | 1 | ModelAndView | user |
| RypController::getRypRemoteWidget | 1 | ModelAndView | user |
| RypController::rypRemoteWidgetPost | 1 | PetsRypReference | user |
| GraffitiController::renderGraffitiWidget | 3 | ModelAndView | user |
| GraffitiController::dismissGraffitiWidget | 0 | void | user |
| GraffitiController::savePetProfile | 3 | AjaxJSONResponse | user |
| GraffitiController::graffitiAddItemsToCart | 1 | AjaxJSONResponse | user |
| CartController::addItemsToCart | 1 | AjaxJSONResponse | user |
| DynamicContentLoader::renderPastPurchases | 3 | ModelAndView | user |
| DynamicContentLoader::fetchPastPurchases | 2 | List | user |
| CarouselAjaxController::execute | 14 | List | user |
| RedemptionPromotionMessageConsumer::processMessage | 1 | void | service-to-service |
| EDXS3MessageConsumer::processMessage | 1 | void | service-to-service |
| ImageDeletionMessageConsumer::processMessage | 1 | void | service-to-service |
| PetPurchaseMessageConsumer::processMessage | 1 | void | service-to-service |

## Appendix B: Per-Agent Metrics Breakdown

| Agent | Invocations | Cost | Time | Input Tokens | Output Tokens |
|-------|-------------|------|------|--------------|---------------|
| consolidate | 7 | $0.7239 | 00:12:28 | 2.4K | 29.4K |
| cvssv4 | 15 | $2.3334 | 00:06:34 | 364.6K | 36.0K |
| deduplicate | 241 | $0.6110 | 00:54:43 | 1.0M | 301.3K |
| entrypoint | 6 | $1.5860 | 00:03:05 | 213.5K | 33.2K |
| ep-analyze | 767 | $42.3976 | 03:30:12 | 27.3M | 8.9M |
| ep-qa | 216 | $49.7797 | 01:50:47 | 7.0M | 868.8K |
| qa | 45 | $21.1521 | 00:22:12 | 2.3M | 282.3K |
| qa-amend | 1 | $0.1712 | 00:00:43 | 24.1K | 3.1K |
| validate | 91 | $17.6978 | 01:04:04 | 4.0M | 673.3K |
| writeup | 15 | $0.6670 | 00:06:55 | 29.3K | 27.2K |
| ws-analyze | 18 | $6.2247 | 00:17:26 | 1.0M | 239.1K |

## Appendix C: Package Commits

| Package | Commit |
|---------|--------|
| PetsProfileService/src/PetsProfileService | `a4d1eae69770` |
| PetsProfileWebsite/src/CoralClientBuilder | `75380708bdfa` |
| PetsProfileWebsite/src/HorizonteFoundationDependencies | `95ba638111da` |
| PetsProfileWebsite/src/PetsProfileWebsite | `65bb9061409c` |

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
