function count_like_dislike(A, P) {
    // You must complete the logic for the function that is provided
    // before compiling or submitting to avoid an error.

    // Write your code here
    let count = 0
    for (let i=0; i< A.length; i++) {
        if (A[i] == P[i]) {
            count = count + 1
        }
    }
    return count

}

const test = count_like_dislike( "11011",  "11000")
console.log(test)